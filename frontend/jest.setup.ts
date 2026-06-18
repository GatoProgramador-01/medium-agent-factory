import "@testing-library/jest-dom";

// Mock next/navigation — usePathname, useRouter, and useParams require the
// Next.js router context which doesn't exist in jsdom. Provide minimal stubs.
jest.mock("next/navigation", () => ({
  usePathname: jest.fn(() => "/"),
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
  })),
  useParams: jest.fn(() => ({})),
}));

// navigator.clipboard is not available in jsdom.
// configurable: true is required so userEvent.setup() can redefine it internally.
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: jest.fn().mockResolvedValue(undefined) },
  writable: true,
  configurable: true,
});

// jsdom does not implement scrollIntoView
window.HTMLElement.prototype.scrollIntoView = jest.fn();
