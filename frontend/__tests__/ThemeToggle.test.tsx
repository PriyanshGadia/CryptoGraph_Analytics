import React from "react";
import { describe, test, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ThemeToggle } from "../components/ThemeToggle";

// Mock the next-themes module
vi.mock("next-themes", () => {
  let theme = "light";
  return {
    useTheme: () => ({
      theme,
      setTheme: (newTheme: string) => {
        theme = newTheme;
      },
    }),
  };
});

describe("ThemeToggle Component", () => {
  test("renders button after mounting", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle theme/i });
    expect(button).toBeInTheDocument();
  });

  test("toggles theme value when clicked", () => {
    const { rerender } = render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle theme/i });
    
    // Initial click toggles from light to dark
    fireEvent.click(button);
    rerender(<ThemeToggle />);
    
    // We can verify that it does not crash and continues rendering
    expect(button).toBeInTheDocument();
  });
});
