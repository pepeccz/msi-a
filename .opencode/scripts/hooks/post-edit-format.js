#!/usr/bin/env node
/**
 * Post-Edit Format Hook
 * Auto-formats files after OpenCode edits them
 */

import { formatFile } from "../lib/formatters.js";

const run = async () => {
  const filePath = process.argv[2];

  if (!filePath) {
    console.error("[Hook] Usage: node post-edit-format.js <filePath>");
    process.exit(1);
  }

  try {
    const result = await formatFile(filePath);
    
    if (result.success) {
      // Only log if actually formatted (not skipped)
      if (!result.message.includes("No formatter") && !result.message.includes("not available")) {
        console.log(`[Hook] ${result.message}`);
      }
    } else {
      console.error(`[Hook] ${result.message}`);
    }
  } catch (error) {
    console.error(`[Hook] Format error: ${error.message}`);
  }
};

run();
