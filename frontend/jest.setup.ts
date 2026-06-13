import "@testing-library/jest-dom";

// Mock next/navigation — usePathname and useRouter require the Next.js router
// context which doesn't exist in jsdom. Provide minimal stubs.
jest.mock("next/navigation", () => ({
  usePathname: jest.fn(() => "/"),
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
  })),
}));

// navigator.clipboard is not available in jsdom
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: jest.fn().mockResolvedValue(undefined) },
  writable: true,
});
