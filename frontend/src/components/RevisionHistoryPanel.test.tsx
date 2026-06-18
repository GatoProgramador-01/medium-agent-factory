import { render, screen } from "@testing-library/react";
import { RevisionHistoryPanel } from "./RevisionHistoryPanel";
import type { QualityHistoryEntry } from "@/lib/api";

function makeEntry(overrides: Partial<QualityHistoryEntry> = {}): QualityHistoryEntry {
  return {
    cycle: 0,
    score: 0.85,
    read_ratio: 0.72,
    boost_eligible: false,
    issue_count: 2,
    passed: false,
    gate_failures: ["score 0.85 below minimum 0.90"],
    issue_categories: [],
    ...overrides,
  };
}

const twoEntries = [
  makeEntry({ cycle: 0 }),
  makeEntry({ cycle: 1, passed: true, score: 0.93, gate_failures: [] }),
];

describe("RevisionHistoryPanel", () => {
  it("returns null when history is undefined", () => {
    const { container } = render(<RevisionHistoryPanel history={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null when history is empty", () => {
    const { container } = render(<RevisionHistoryPanel history={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null when history has only one entry", () => {
    const { container } = render(<RevisionHistoryPanel history={[makeEntry()]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders heading when 2 or more entries", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("revision-history-heading")).toBeInTheDocument();
  });

  it("shows cycle count in heading", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("revision-history-heading")).toHaveTextContent("2");
  });

  it("renders a row for each cycle", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("cycle-item-0")).toBeInTheDocument();
    expect(screen.getByTestId("cycle-item-1")).toBeInTheDocument();
  });

  it("shows PASS badge for passed cycles", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("cycle-item-1")).toHaveTextContent("PASS");
  });

  it("shows FAIL badge for failed cycles", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("cycle-item-0")).toHaveTextContent("FAIL");
  });

  it("shows gate failure reason under a failed cycle", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("cycle-item-0")).toHaveTextContent("score 0.85 below minimum");
  });

  it("does not show gate failure text on a passing cycle", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    const passingRow = screen.getByTestId("cycle-item-1");
    expect(passingRow).not.toHaveTextContent("below");
  });

  it("shows the score value for each cycle", () => {
    render(<RevisionHistoryPanel history={twoEntries} />);
    expect(screen.getByTestId("cycle-item-0")).toHaveTextContent("85");
    expect(screen.getByTestId("cycle-item-1")).toHaveTextContent("93");
  });
});
