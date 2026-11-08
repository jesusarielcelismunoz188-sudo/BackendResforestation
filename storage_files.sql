-- Configura un bucket privado y el catálogo de archivos adjuntos.
-- Ejecutar una vez en Supabase SQL Editor o contra la BD local de Supabase.
-- La clave secreta de Supabase no se necesita para estas operaciones.

BEGIN;

INSERT INTO storage.buckets (
    id, name, public, file_size_limit, allowed_mime_types
)
VALUES (
    'reforestacion-archivos',
    'reforestacion-archivos',
    false,
    10485760,
    ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

CREATE TABLE IF NOT EXISTS public.archivos_adjuntos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type text NOT NULL CHECK (entity_type IN ('proyecto', 'predio', 'lote')),
    entity_id uuid NOT NULL,
    category text NOT NULL CHECK (
        category IN ('project_document', 'field_photo', 'soil_report')
    ),
    original_name text NOT NULL,
    content_type text NOT NULL CHECK (
        content_type IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')
    ),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 10485760),
    object_path text NOT NULL UNIQUE,
    uploaded_by uuid NOT NULL REFERENCES public.perfiles(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (category = 'project_document' AND entity_type = 'proyecto')
        OR (category = 'field_photo' AND entity_type IN ('predio', 'lote'))
        OR (category = 'soil_report' AND entity_type = 'lote')
    )
);

CREATE INDEX IF NOT EXISTS archivos_adjuntos_entity_idx
    ON public.archivos_adjuntos (entity_type, entity_id, category, created_at DESC);
CREATE INDEX IF NOT EXISTS archivos_adjuntos_owner_idx
    ON public.archivos_adjuntos (uploaded_by, created_at DESC);

ALTER TABLE public.archivos_adjuntos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS archivos_adjuntos_propios ON public.archivos_adjuntos;
CREATE POLICY archivos_adjuntos_propios
    ON public.archivos_adjuntos
    FOR ALL
    TO authenticated
    USING (uploaded_by = (SELECT auth.uid()))
    WITH CHECK (uploaded_by = (SELECT auth.uid()));

DROP POLICY IF EXISTS "reforestacion_archivos_select_own" ON storage.objects;
CREATE POLICY "reforestacion_archivos_select_own"
    ON storage.objects
    FOR SELECT
    TO authenticated
    USING (
        bucket_id = 'reforestacion-archivos'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::text
    );

DROP POLICY IF EXISTS "reforestacion_archivos_insert_own" ON storage.objects;
CREATE POLICY "reforestacion_archivos_insert_own"
    ON storage.objects
    FOR INSERT
    TO authenticated
    WITH CHECK (
        bucket_id = 'reforestacion-archivos'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::text
    );

DROP POLICY IF EXISTS "reforestacion_archivos_delete_own" ON storage.objects;
CREATE POLICY "reforestacion_archivos_delete_own"
    ON storage.objects
    FOR DELETE
    TO authenticated
    USING (
        bucket_id = 'reforestacion-archivos'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::text
    );

COMMIT;
