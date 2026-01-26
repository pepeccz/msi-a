import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ElementsTreeSection } from "../elements-tree-section";
import type { Element } from "@/lib/types";
import type { ElementTreeNode } from "@/hooks/use-category-elements";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

describe("ElementsTreeSection", () => {
  const mockElements: Element[] = [
    {
      id: "1",
      code: "ESCAPE",
      name: "Sistema de escape",
      keywords: ["escape", "tubo", "silenciador"],
      is_active: true,
      image_count: 2,
      warning_count: 0,
      category_id: "cat-1",
      sort_order: 1,
    } as Element,
  ];

  const mockTree: ElementTreeNode[] = [
    {
      ...mockElements[0],
      children: [],
    },
  ];

  const defaultProps = {
    elements: mockElements,
    elementTree: mockTree,
    isLoading: false,
    onCreateElement: jest.fn(),
    onDeleteElement: jest.fn(),
  };

  it("renders without crashing", () => {
    render(<ElementsTreeSection {...defaultProps} />);
    expect(screen.getByText("Elementos de la Categoria")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    render(<ElementsTreeSection {...defaultProps} isLoading={true} />);
    expect(screen.getByText("Cargando elementos...")).toBeInTheDocument();
  });

  it("shows empty state when no elements", () => {
    render(
      <ElementsTreeSection
        {...defaultProps}
        elements={[]}
        elementTree={[]}
      />
    );
    expect(screen.getByText("No hay elementos configurados")).toBeInTheDocument();
  });

  it("filters elements by search query", async () => {
    render(<ElementsTreeSection {...defaultProps} />);

    const searchInput = screen.getByPlaceholderText(/buscar/i);
    fireEvent.change(searchInput, { target: { value: "escape" } });

    // Wait for debounce
    await waitFor(() => {
      expect(screen.getByText("Sistema de escape")).toBeInTheDocument();
    }, { timeout: 500 });
  });

  it("handles malformed keywords gracefully", () => {
    const malformedElement: Element = {
      id: "2",
      code: "BAD",
      name: "Bad Element",
      keywords: "not-an-array" as any, // Invalid type
      is_active: true,
      category_id: "cat-1",
      sort_order: 2,
    } as Element;

    const malformedTree: ElementTreeNode[] = [
      { ...malformedElement, children: [] },
    ];

    // Should not crash thanks to defensive checks
    expect(() =>
      render(
        <ElementsTreeSection
          {...defaultProps}
          elements={[malformedElement]}
          elementTree={malformedTree}
        />
      )
    ).not.toThrow();
  });

  it("calls onCreateElement when button clicked", () => {
    const onCreateElement = jest.fn();
    render(<ElementsTreeSection {...defaultProps} onCreateElement={onCreateElement} />);

    const createButton = screen.getAllByText("Nuevo Elemento")[0];
    fireEvent.click(createButton);

    expect(onCreateElement).toHaveBeenCalledTimes(1);
  });

  it("expands/collapses parent elements", async () => {
    const parentWithChildren: ElementTreeNode = {
      id: "parent",
      code: "PARENT",
      name: "Parent Element",
      keywords: [],
      is_active: true,
      category_id: "cat-1",
      sort_order: 1,
      children: [
        {
          id: "child",
          code: "CHILD",
          name: "Child Element",
          keywords: [],
          is_active: true,
          category_id: "cat-1",
          sort_order: 1,
          parent_element_id: "parent",
        } as Element,
      ],
    };

    render(
      <ElementsTreeSection
        {...defaultProps}
        elements={[parentWithChildren, ...parentWithChildren.children]}
        elementTree={[parentWithChildren]}
      />
    );

    // Initially collapsed
    expect(screen.queryByText("Child Element")).not.toBeInTheDocument();

    // Click expand button
    const expandButton = screen.getByLabelText("Expandir elemento");
    fireEvent.click(expandButton);

    // Should show child
    await waitFor(() => {
      expect(screen.getByText("Child Element")).toBeInTheDocument();
    });

    // Click collapse button
    const collapseButton = screen.getByLabelText("Contraer elemento");
    fireEvent.click(collapseButton);

    // Should hide child
    await waitFor(() => {
      expect(screen.queryByText("Child Element")).not.toBeInTheDocument();
    });
  });

  it("has accessible labels for interactive elements", () => {
    render(<ElementsTreeSection {...defaultProps} />);

    const searchInput = screen.getByLabelText("Buscar elementos");
    expect(searchInput).toBeInTheDocument();

    const manageButton = screen.getByLabelText(/Gestionar elemento/);
    expect(manageButton).toBeInTheDocument();

    const deleteButton = screen.getByLabelText(/Eliminar elemento/);
    expect(deleteButton).toBeInTheDocument();
  });

  it("displays keywords with MAX_VISIBLE_KEYWORDS limit", () => {
    const elementWithManyKeywords: Element = {
      id: "3",
      code: "MANY_KW",
      name: "Element with Many Keywords",
      keywords: ["kw1", "kw2", "kw3", "kw4", "kw5"],
      is_active: true,
      category_id: "cat-1",
      sort_order: 3,
    } as Element;

    const tree: ElementTreeNode[] = [
      { ...elementWithManyKeywords, children: [] },
    ];

    render(
      <ElementsTreeSection
        {...defaultProps}
        elements={[elementWithManyKeywords]}
        elementTree={tree}
      />
    );

    // Should show +2 more badge (5 keywords - 3 visible = 2)
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});
