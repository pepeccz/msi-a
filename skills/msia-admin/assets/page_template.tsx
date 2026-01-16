/**
 * Template for MSI-a Admin Panel page.
 *
 * Usage:
 * 1. Copy this file to admin-panel/src/app/(authenticated)/your-section/
 * 2. Rename to page.tsx
 * 3. Update the component name and content
 * 4. Add navigation link in sidebar if needed
 */

import { Suspense } from "react";
import { Metadata } from "next";
import { MyResourceList } from "@/components/my-resource/my-resource-list";
import { MyResourceListSkeleton } from "@/components/my-resource/my-resource-list-skeleton";
import { CreateResourceDialog } from "@/components/my-resource/create-resource-dialog";

export const metadata: Metadata = {
  title: "Mi Recurso | MSI-a Admin",
  description: "Gestión de recursos",
};

export default function MyResourcePage() {
  return (
    <div className="container mx-auto py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Mi Recurso</h1>
          <p className="text-muted-foreground">
            Gestiona los recursos del sistema
          </p>
        </div>
        <CreateResourceDialog />
      </div>

      {/* Content with Suspense boundary */}
      <Suspense fallback={<MyResourceListSkeleton />}>
        <MyResourceList />
      </Suspense>
    </div>
  );
}

// =============================================================================
// Alternative: Page with server-side data fetching
// =============================================================================

/*
import { api } from "@/lib/api";

interface MyResource {
  id: string;
  name: string;
  // ... other fields
}

async function getResources(): Promise<MyResource[]> {
  // This runs on the server
  const response = await fetch(`${process.env.API_URL}/api/my-resource`, {
    cache: "no-store", // or "force-cache" for static
  });
  
  if (!response.ok) {
    throw new Error("Failed to fetch resources");
  }
  
  return response.json();
}

export default async function MyResourcePage() {
  const resources = await getResources();
  
  return (
    <div className="container mx-auto py-6">
      <h1 className="text-2xl font-bold mb-6">Mi Recurso</h1>
      <MyResourceTable data={resources} />
    </div>
  );
}
*/

// =============================================================================
// Alternative: Dynamic route page
// =============================================================================

/*
// app/(authenticated)/my-resource/[id]/page.tsx

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const resource = await getResource(id);
  
  return {
    title: `${resource?.name ?? "Recurso"} | MSI-a Admin`,
  };
}

export default async function ResourceDetailPage({ params }: PageProps) {
  const { id } = await params;
  const resource = await getResource(id);
  
  if (!resource) {
    notFound();
  }
  
  return (
    <div className="container mx-auto py-6">
      <h1 className="text-2xl font-bold">{resource.name}</h1>
      <ResourceDetails resource={resource} />
    </div>
  );
}
*/
