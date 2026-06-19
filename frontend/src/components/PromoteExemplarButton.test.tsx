import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PromoteExemplarButton } from "./PromoteExemplarButton";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: { promoteExemplar: jest.fn() },
}));

describe("PromoteExemplarButton", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Save as Exemplar button", () => {
    render(<PromoteExemplarButton runId="run-1" />);
    expect(screen.getByRole("button", { name: /save as exemplar/i })).toBeInTheDocument();
  });

  it("calls api.promoteExemplar with the runId on click", async () => {
    const user = userEvent.setup();
    (api.promoteExemplar as jest.Mock).mockResolvedValue({ run_id: "run-1", status: "saved_as_exemplar" });
    render(<PromoteExemplarButton runId="run-1" />);
    await user.click(screen.getByRole("button", { name: /save as exemplar/i }));
    expect(api.promoteExemplar).toHaveBeenCalledWith("run-1");
  });

  it("shows Saved! after successful promote", async () => {
    const user = userEvent.setup();
    (api.promoteExemplar as jest.Mock).mockResolvedValue({ run_id: "run-1", status: "saved_as_exemplar" });
    render(<PromoteExemplarButton runId="run-1" />);
    await user.click(screen.getByRole("button", { name: /save as exemplar/i }));
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("Saved!"));
  });

  it("button is disabled while the request is in flight", async () => {
    const user = userEvent.setup();
    (api.promoteExemplar as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PromoteExemplarButton runId="run-1" />);
    await user.click(screen.getByRole("button", { name: /save as exemplar/i }));
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("shows Saving… label while request is in flight", async () => {
    const user = userEvent.setup();
    (api.promoteExemplar as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PromoteExemplarButton runId="run-1" />);
    await user.click(screen.getByRole("button", { name: /save as exemplar/i }));
    expect(screen.getByRole("button")).toHaveTextContent("Saving…");
  });

  it("returns to idle state after API error", async () => {
    const user = userEvent.setup();
    (api.promoteExemplar as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<PromoteExemplarButton runId="run-1" />);
    await user.click(screen.getByRole("button", { name: /save as exemplar/i }));
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent(/save as exemplar/i)
    );
    expect(screen.getByRole("button")).toBeEnabled();
  });
});
