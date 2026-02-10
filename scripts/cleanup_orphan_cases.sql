-- ============================================================================
-- Phase 4: Identify and Clean Orphan Cases
-- 
-- Context: Before the bugfix (Phase 1-2), iniciar_expediente would create
-- Case records in the DB with status='collecting' but the agent never
-- transitioned to EXPEDIENTE_MODE to actually collect data. These are orphans.
--
-- IMPORTANT: Run the SELECT queries FIRST to review before executing UPDATE.
-- ============================================================================

-- STEP 1: Identify orphan cases
-- Cases with status='collecting' that have NO element data, NO images, 
-- and NO personal data collected (indicating they were never processed)
SELECT 
    c.id,
    c.conversation_id,
    c.status,
    c.created_at,
    c.updated_at,
    c.vehiculo_marca,
    c.vehiculo_modelo,
    c.element_codes,
    c.tariff_amount,
    (SELECT COUNT(*) FROM case_images ci WHERE ci.case_id = c.id) AS image_count,
    (SELECT COUNT(*) FROM case_element_data ced WHERE ced.case_id = c.id) AS element_data_count
FROM cases c
WHERE c.status = 'collecting'
  AND c.created_at < NOW() - INTERVAL '24 hours'  -- Older than 24h (not currently active)
ORDER BY c.created_at DESC;

-- STEP 2: Count how many orphans exist
SELECT 
    COUNT(*) AS total_collecting,
    COUNT(*) FILTER (
        WHERE NOT EXISTS (SELECT 1 FROM case_images ci WHERE ci.case_id = c.id)
          AND NOT EXISTS (SELECT 1 FROM case_element_data ced WHERE ced.case_id = c.id)
    ) AS likely_orphans
FROM cases c
WHERE c.status = 'collecting'
  AND c.created_at < NOW() - INTERVAL '24 hours';

-- STEP 3: Mark orphans as 'abandoned' (soft update, NOT delete)
-- UNCOMMENT AND RUN ONLY AFTER REVIEWING STEP 1 AND 2 RESULTS
/*
UPDATE cases
SET 
    status = 'abandoned',
    updated_at = NOW()
WHERE status = 'collecting'
  AND created_at < NOW() - INTERVAL '24 hours'
  AND NOT EXISTS (SELECT 1 FROM case_images ci WHERE ci.case_id = cases.id)
  AND NOT EXISTS (SELECT 1 FROM case_element_data ced WHERE ced.case_id = cases.id);
*/

-- STEP 4: Verify the cleanup
-- SELECT status, COUNT(*) FROM cases GROUP BY status ORDER BY status;
