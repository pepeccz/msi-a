import React from "react";
import { render } from "@testing-library/react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../table";

// Minimal wrapper to render a well-formed table
function BasicTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Columna A</TableHead>
          <TableHead>Columna B</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell>Celda 1</TableCell>
          <TableCell>Celda 2</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  );
}

describe("Table primitive (Slice 2 — T2.1/T2.3)", () => {
  it("renders a native <table> element (HTML semantics preserved)", () => {
    const { container } = render(<BasicTable />);
    expect(container.querySelector("table")).not.toBeNull();
  });

  it("<table> has group/table class (named group for density selectors)", () => {
    const { container } = render(<BasicTable />);
    const table = container.querySelector("table");
    expect(table).toHaveClass("group/table");
  });

  it("<table> has data-density attribute (density toggle anchor)", () => {
    const { container } = render(<BasicTable />);
    const table = container.querySelector("table");
    expect(table).toHaveAttribute("data-density");
  });

  it("<thead> has bg-muted/30 class (subtle header background — T2.1)", () => {
    const { container } = render(<BasicTable />);
    const thead = container.querySelector("thead");
    // Tailwind generates the class literally as "bg-muted/30"
    expect(thead?.className).toContain("bg-muted/30");
  });

  it("<thead> retains [&_tr]:border-b class (border preserved)", () => {
    const { container } = render(<BasicTable />);
    const thead = container.querySelector("thead");
    expect(thead?.className).toContain("[&_tr]:border-b");
  });

  it("<td> has compact density classes (density selectors intact)", () => {
    const { container } = render(<BasicTable />);
    const td = container.querySelector("td");
    expect(td?.className).toContain("group-data-[density=compact]/table:py-1");
    expect(td?.className).toContain("group-data-[density=compact]/table:px-2");
  });
});
