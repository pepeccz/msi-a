/**
 * Tests for ErrorCard component.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorCard } from "../error-card";

describe("ErrorCard", () => {
  // (a) Renders message
  it("renders the message prop", () => {
    render(<ErrorCard message="No se pudieron cargar los usuarios" />);
    expect(
      screen.getByText("No se pudieron cargar los usuarios")
    ).toBeInTheDocument();
  });

  it("renders default message when no message prop", () => {
    render(<ErrorCard />);
    expect(
      screen.getByText(/No se pudo cargar la información/i)
    ).toBeInTheDocument();
  });

  // (b) Renders "Reintentar" button ONLY when onRetry provided
  it("renders Reintentar button when onRetry is provided", () => {
    render(<ErrorCard onRetry={jest.fn()} />);
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });

  it("does NOT render Reintentar button when onRetry is not provided", () => {
    render(<ErrorCard />);
    expect(screen.queryByRole("button", { name: /reintentar/i })).toBeNull();
  });

  // (c) Calls onRetry on button click
  it("calls onRetry when Reintentar button is clicked", () => {
    const onRetry = jest.fn();
    render(<ErrorCard onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /reintentar/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  // (d) Does not render stack trace in production env
  it("does NOT render <details> in production environment", () => {
    const originalEnv = process.env.NODE_ENV;
    Object.defineProperty(process.env, "NODE_ENV", {
      value: "production",
      configurable: true,
    });

    const error = new Error("some internal error");
    render(<ErrorCard error={error} />);

    expect(screen.queryByRole("group")).toBeNull(); // <details> renders as group
    expect(screen.queryByText(/some internal error/i)).toBeNull();

    Object.defineProperty(process.env, "NODE_ENV", {
      value: originalEnv,
      configurable: true,
    });
  });

  // (e) Renders <details> when error is Error instance in dev env
  it("renders <details> with error info in development environment", () => {
    // NODE_ENV is "test" by default in Jest — close enough to development behavior
    // We simulate dev by checking the condition: NODE_ENV !== 'production'
    const error = new Error("dev-only message");
    render(<ErrorCard error={error} />);

    // Should find "Detalles técnicos" summary
    expect(screen.getByText(/Detalles técnicos/i)).toBeInTheDocument();
  });

  it("does NOT render <details> when error is not an Error instance", () => {
    render(<ErrorCard error={{ code: 500 }} />);
    expect(screen.queryByText(/Detalles técnicos/i)).toBeNull();
  });

  // Variant rendering
  it("renders inline variant without centering wrapper", () => {
    const { container } = render(<ErrorCard variant="inline" />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain("w-full");
    expect(wrapper.className).not.toContain("min-h-");
  });

  it("renders page variant with centered wrapper", () => {
    const { container } = render(<ErrorCard variant="page" />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain("min-h-");
    expect(wrapper.className).toContain("items-center");
  });

  // Title rendering
  it("renders custom title", () => {
    render(<ErrorCard title="Error personalizado" />);
    expect(screen.getByText("Error personalizado")).toBeInTheDocument();
  });
});
