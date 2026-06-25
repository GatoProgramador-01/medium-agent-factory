# Infrastructure — medium-agent-factory

Terraform for deploying the FastAPI backend to AWS. The frontend stays on Vercel (zero-config CDN, free tier). MongoDB Atlas remains external (no AWS cost, no ops burden).

Two deployment options are provided. Pick one — they are independent.

---

## Option A vs Option B

| | App Runner (`app-runner/`) | ECS Fargate (`ecs/`) |
|---|---|---|
| **Cost** | ~$15-20/month | ~$25-40/month |
| **Ops burden** | Minimal — no VPC, ALB, or SGs to manage | Moderate — VPC, ALB, SGs, CloudWatch alarms |
| **Networking** | Managed by AWS | Full VPC control |
| **Scaling** | Auto, concurrency-based | Manual desired_count or App Auto Scaling |
| **Use when** | Portfolio, low traffic, fast setup | Need WAF, private subnets, custom routing |
| **Cold start** | ~5s (managed) | ~30s (ECS task startup) |

**Recommendation for this portfolio project:** start with App Runner. Switch to ECS when you need WAF, blue/green deployments via CodeDeploy, or private subnet isolation.

---

## Step 0 — Bootstrap state backend (run once)

Terraform needs an S3 bucket and DynamoDB table before any remote state can be stored.

```bash
cd infra/bootstrap
terraform init
terraform apply
```

Copy the `backend_config` output and paste it into `infra/app-runner/main.tf` or `infra/ecs/main.tf` (the `backend "s3"` block is already in the file, commented out).

---

## Step 1 — Store secrets in SSM Parameter Store

**Never** put secrets in Terraform variables or `.tfvars` files committed to git.

Run these four commands, replacing the placeholder values with real secrets:

```bash
aws ssm put-parameter \
  --name "/medium-agent-factory/prod/MONGODB_URI" \
  --value "mongodb+srv://user:pass@cluster.mongodb.net/dbname" \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name "/medium-agent-factory/prod/ANTHROPIC_API_KEY" \
  --value "sk-ant-..." \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name "/medium-agent-factory/prod/TAVILY_API_KEY" \
  --value "tvly-..." \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name "/medium-agent-factory/prod/LANGCHAIN_API_KEY" \
  --value "ls__..." \
  --type SecureString \
  --overwrite
```

Verify the parameters exist before running `terraform apply`:

```bash
aws ssm get-parameters-by-path \
  --path "/medium-agent-factory/prod/" \
  --with-decryption \
  --query "Parameters[*].Name"
```

---

## Step 2 — Build and push the Docker image to ECR

```bash
# Create the ECR repository (one-time)
aws ecr create-repository \
  --repository-name medium-agent-factory-backend \
  --image-scanning-configuration scanOnPush=true \
  --tags Key=Project,Value=medium-agent-factory Key=ManagedBy,Value=terraform

# Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t medium-agent-factory-backend ./backend
docker tag medium-agent-factory-backend:latest \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend:latest
docker push \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend:latest
```

---

## Step 3 — Deploy Option A (App Runner)

```bash
cd infra/app-runner

terraform init

terraform plan \
  -var="image_uri=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend:latest"

terraform apply \
  -var="image_uri=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend:latest"
```

The service URL is printed as the `service_url` output.

### Using a public GHCR image instead of ECR

If the image is on GitHub Container Registry (public):

1. Change `image_repository_type` to `"ECR_PUBLIC"` in `app-runner/main.tf`.
2. Remove the `authentication_configuration` block.
3. Set `image_uri` to `ghcr.io/<owner>/medium-agent-factory-backend:latest`.

---

## Step 4 — Deploy Option B (ECS Fargate)

```bash
cd infra/ecs

terraform init

terraform plan \
  -var="ecr_repository_url=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend" \
  -var="image_tag=latest"

terraform apply \
  -var="ecr_repository_url=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend" \
  -var="image_tag=latest"
```

The ALB DNS name is printed as the `alb_dns_name` output. Point your domain's CNAME to it.

---

## Deploying a new image version (ECS)

After pushing a new tag to ECR, force a new deployment without changing Terraform state:

```bash
aws ecs update-service \
  --cluster medium-agent-factory-prod-cluster \
  --service medium-agent-factory-prod-backend \
  --force-new-deployment
```

Or update `var.image_tag` and run `terraform apply` — the task definition is re-registered with the new image URI and ECS rolls it out.

---

## Cost estimates

### App Runner (Option A)

| Resource | Cost |
|---|---|
| App Runner (1 vCPU / 2 GB, 1 instance, ~730h) | ~$14/month |
| ECR storage (< 1 GB image) | ~$0.10/month |
| SSM Parameter Store (4 SecureString params) | ~$0.40/month |
| **Total** | **~$15/month** |

### ECS Fargate (Option B)

| Resource | Cost |
|---|---|
| ECS Fargate (0.5 vCPU / 1 GB, 1 task, ~730h) | ~$13/month |
| ALB (~1 LCU) | ~$16/month |
| CloudWatch Logs (30-day retention) | ~$1/month |
| ECR + SSM | ~$0.50/month |
| **Total** | **~$30/month** |

Cost increases if desired_count > 1 or if Container Insights metrics are heavy.

---

## Tear down

```bash
# App Runner
cd infra/app-runner && terraform destroy

# ECS
cd infra/ecs && terraform destroy

# Bootstrap (only when nothing else references the state bucket)
# Remove lifecycle { prevent_destroy = true } first, then:
cd infra/bootstrap && terraform destroy
```
