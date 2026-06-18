import { render, screen } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { NavLinks } from "./NavLinks";

describe("NavLinks", () => {
  it("renders all six navigation links", () => {
    (usePathname as jest.Mock).mockReturnValue("/");
    render(<NavLinks />);
    expect(screen.getByTestId("nav-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("nav-pipeline")).toBeInTheDocument();
    expect(screen.getByTestId("nav-posts")).toBeInTheDocument();
    expect(screen.getByTestId("nav-series")).toBeInTheDocument();
    expect(screen.getByTestId("nav-exemplars")).toBeInTheDocument();
    expect(screen.getByTestId("nav-analytics")).toBeInTheDocument();
  });

  it("each link points to the correct href", () => {
    (usePathname as jest.Mock).mockReturnValue("/");
    render(<NavLinks />);
    expect(screen.getByTestId("nav-dashboard")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("nav-pipeline")).toHaveAttribute("href", "/pipeline");
    expect(screen.getByTestId("nav-posts")).toHaveAttribute("href", "/posts");
    expect(screen.getByTestId("nav-series")).toHaveAttribute("href", "/series");
    expect(screen.getByTestId("nav-exemplars")).toHaveAttribute("href", "/exemplars");
    expect(screen.getByTestId("nav-analytics")).toHaveAttribute("href", "/analytics");
  });

  it("Dashboard link is active when pathname is /", () => {
    (usePathname as jest.Mock).mockReturnValue("/");
    render(<NavLinks />);
    expect(screen.getByTestId("nav-dashboard")).toHaveStyle({ color: "var(--orange)" });
  });

  it("Dashboard link is NOT active when pathname is /posts", () => {
    (usePathname as jest.Mock).mockReturnValue("/posts");
    render(<NavLinks />);
    expect(screen.getByTestId("nav-dashboard")).not.toHaveStyle({ color: "var(--orange)" });
  });

  it("Posts link is active when pathname starts with /posts", () => {
    (usePathname as jest.Mock).mockReturnValue("/posts/run-abc");
    render(<NavLinks />);
    expect(screen.getByTestId("nav-posts")).toHaveStyle({ color: "var(--orange)" });
  });

  it("Exemplars link is active when pathname is /exemplars", () => {
    (usePathname as jest.Mock).mockReturnValue("/exemplars");
    render(<NavLinks />);
    expect(screen.getByTestId("nav-exemplars")).toHaveStyle({ color: "var(--orange)" });
  });

  it("only one link is active at a time", () => {
    (usePathname as jest.Mock).mockReturnValue("/analytics");
    render(<NavLinks />);
    const orange = "var(--orange)";
    const activeLinks = [
      screen.getByTestId("nav-dashboard"),
      screen.getByTestId("nav-pipeline"),
      screen.getByTestId("nav-posts"),
      screen.getByTestId("nav-series"),
      screen.getByTestId("nav-exemplars"),
      screen.getByTestId("nav-analytics"),
    ].filter((el) => el.getAttribute("style")?.includes(orange));
    expect(activeLinks).toHaveLength(1);
    expect(activeLinks[0]).toBe(screen.getByTestId("nav-analytics"));
  });
});
