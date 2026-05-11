import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { FilterChips } from "../filter-chips";

const OPTIONS = [
  { value: "all", label: "Todos", count: 42 },
  { value: "pending", label: "Pendientes", count: 7 },
  { value: "in_progress", label: "En Progreso", count: 3 },
  { value: "resolved", label: "Resueltas", count: 0 },
];

describe("FilterChips", () => {
  it("renders all options with their labels", () => {
    render(<FilterChips options={OPTIONS} value={null} onChange={jest.fn()} />);

    expect(screen.getByRole("button", { name: /Todos/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pendientes/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /En Progreso/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Resueltas/ })).toBeInTheDocument();
  });

  it("renders count badges for each option", () => {
    render(<FilterChips options={OPTIONS} value={null} onChange={jest.fn()} />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("active chip has aria-pressed='true', others have aria-pressed='false'", () => {
    render(<FilterChips options={OPTIONS} value="pending" onChange={jest.fn()} />);

    const allBtn = screen.getByRole("button", { name: /Todos/ });
    const pendingBtn = screen.getByRole("button", { name: /Pendientes/ });
    const progressBtn = screen.getByRole("button", { name: /En Progreso/ });

    expect(pendingBtn).toHaveAttribute("aria-pressed", "true");
    expect(allBtn).toHaveAttribute("aria-pressed", "false");
    expect(progressBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking an inactive chip calls onChange with the chip value", () => {
    const handleChange = jest.fn();
    render(<FilterChips options={OPTIONS} value="all" onChange={handleChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Pendientes/ }));

    expect(handleChange).toHaveBeenCalledWith("pending");
    expect(handleChange).toHaveBeenCalledTimes(1);
  });

  it("clicking the active chip calls onChange with null (deselect)", () => {
    const handleChange = jest.fn();
    render(<FilterChips options={OPTIONS} value="pending" onChange={handleChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Pendientes/ }));

    expect(handleChange).toHaveBeenCalledWith(null);
    expect(handleChange).toHaveBeenCalledTimes(1);
  });

  it("zero-count chip is rendered but has opacity-60 class when inactive", () => {
    render(<FilterChips options={OPTIONS} value={null} onChange={jest.fn()} />);

    const resolvedBtn = screen.getByRole("button", { name: /Resueltas/ });
    expect(resolvedBtn).toBeInTheDocument();
    expect(resolvedBtn).toHaveClass("opacity-60");
  });

  it("zero-count chip does NOT have opacity-60 when it is the active chip", () => {
    render(<FilterChips options={OPTIONS} value="resolved" onChange={jest.fn()} />);

    const resolvedBtn = screen.getByRole("button", { name: /Resueltas/ });
    expect(resolvedBtn).not.toHaveClass("opacity-60");
    expect(resolvedBtn).toHaveAttribute("aria-pressed", "true");
  });

  it("group element has role='group' and the default aria-label", () => {
    render(<FilterChips options={OPTIONS} value={null} onChange={jest.fn()} />);

    const group = screen.getByRole("group");
    expect(group).toBeInTheDocument();
    expect(group).toHaveAttribute("aria-label", "Filtrar por estado");
  });

  it("group element respects a custom aria-label", () => {
    render(
      <FilterChips
        options={OPTIONS}
        value={null}
        onChange={jest.fn()}
        aria-label="Filtrar escalaciones"
      />,
    );

    expect(screen.getByRole("group")).toHaveAttribute(
      "aria-label",
      "Filtrar escalaciones",
    );
  });

  it("no count badge is rendered when count is undefined", () => {
    const optionsNoCounts = [
      { value: "a", label: "Opcion A" },
      { value: "b", label: "Opcion B" },
    ];
    render(<FilterChips options={optionsNoCounts} value={null} onChange={jest.fn()} />);

    // Labels are present
    expect(screen.getByText("Opcion A")).toBeInTheDocument();
    // No numeric count text
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText("1")).not.toBeInTheDocument();
  });
});
