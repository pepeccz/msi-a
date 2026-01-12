import { useState, useEffect } from "react";
import api from "@/lib/api";
import type { TariffTier, TierElementsPreview } from "@/lib/types";

/**
 * Hook to fetch element counts for all tiers in a category.
 * Uses Promise.all for parallel fetching.
 */
export function useTierElements(tiers: TariffTier[] | undefined) {
  const [tierElementCounts, setTierElementCounts] = useState<Record<string, TierElementsPreview>>({});
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    async function fetchElementCounts() {
      if (!tiers || tiers.length === 0) return;

      setIsLoading(true);
      const counts: Record<string, TierElementsPreview> = {};

      await Promise.all(
        tiers.map(async (tier) => {
          try {
            const preview = await api.getTierResolvedElements(tier.id);
            counts[tier.id] = preview;
          } catch (err) {
            console.error(`Failed to fetch elements for tier ${tier.id}:`, err);
            counts[tier.id] = {
              tier_id: tier.id,
              tier_code: tier.code,
              tier_name: tier.name,
              total_elements: 0,
              elements: {},
            };
          }
        })
      );

      setTierElementCounts(counts);
      setIsLoading(false);
    }

    fetchElementCounts();
  }, [tiers]);

  return { tierElementCounts, isLoading };
}
