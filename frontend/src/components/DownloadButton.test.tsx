import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DownloadButton } from "./DownloadButton";

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsText(blob);
  });
}

describe("DownloadButton", () => {
  beforeEach(() => {
    URL.createObjectURL = jest.fn().mockReturnValue("blob:fake-url");
    URL.revokeObjectURL = jest.fn();
    // Stub anchor click so jsdom doesn't attempt navigation
    jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders a Download .md button", () => {
    render(<DownloadButton title="My Post" content="Content here" />);
    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
  });

  it("shows Downloaded! briefly after clicking", async () => {
    const user = userEvent.setup();
    render(<DownloadButton title="My Post" content="Content here" />);
    await user.click(screen.getByRole("button", { name: /download/i }));
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent("Downloaded!")
    );
  });

  it("calls URL.createObjectURL with a Blob on click", async () => {
    const user = userEvent.setup();
    render(<DownloadButton title="My Post" content="Content here" />);
    await user.click(screen.getByRole("button", { name: /download/i }));
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  });

  it("Blob content includes the post title as an H1", async () => {
    const user = userEvent.setup();
    render(<DownloadButton title="Great Title" content="Body content" />);
    await user.click(screen.getByRole("button", { name: /download/i }));
    const blob = (URL.createObjectURL as jest.Mock).mock.calls[0][0] as Blob;
    expect(await readBlob(blob)).toContain("# Great Title");
  });

  it("Blob content includes the post body", async () => {
    const user = userEvent.setup();
    render(<DownloadButton title="Title" content="The actual body text" />);
    await user.click(screen.getByRole("button", { name: /download/i }));
    const blob = (URL.createObjectURL as jest.Mock).mock.calls[0][0] as Blob;
    expect(await readBlob(blob)).toContain("The actual body text");
  });

  it("revokes the object URL after download", async () => {
    const user = userEvent.setup();
    render(<DownloadButton title="Title" content="Content" />);
    await user.click(screen.getByRole("button", { name: /download/i }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });
});
