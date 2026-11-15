-- Rename provider-specific object columns to neutral names.
-- Exact inverse (run in reverse order when rolling back):
-- ALTER TABLE image_batch_items RENAME COLUMN object_key TO gcs_object;
-- ALTER TABLE pending_papers RENAME COLUMN object_key TO gcs_object;
-- ALTER TABLE papers RENAME COLUMN served_object_key TO served_object;
-- ALTER TABLE papers RENAME COLUMN object_key TO gcs_object;
-- (If the serving bridge has already added this column to pending_papers:)
-- ALTER TABLE pending_papers RENAME COLUMN served_object_key TO served_object;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='papers' AND column_name='gcs_object')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='papers' AND column_name='object_key') THEN
        ALTER TABLE papers RENAME COLUMN gcs_object TO object_key;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='papers' AND column_name='served_object')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='papers' AND column_name='served_object_key') THEN
        ALTER TABLE papers RENAME COLUMN served_object TO served_object_key;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pending_papers' AND column_name='gcs_object')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pending_papers' AND column_name='object_key') THEN
        ALTER TABLE pending_papers RENAME COLUMN gcs_object TO object_key;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pending_papers' AND column_name='served_object')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pending_papers' AND column_name='served_object_key') THEN
        ALTER TABLE pending_papers RENAME COLUMN served_object TO served_object_key;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='image_batch_items' AND column_name='gcs_object')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='image_batch_items' AND column_name='object_key') THEN
        ALTER TABLE image_batch_items RENAME COLUMN gcs_object TO object_key;
    END IF;
END $$;
