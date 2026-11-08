-- Datos de demostración locales para probar el flujo territorial, diagnóstico,
-- selección botánica y logística. Ejecutar después de reforest_schema.sql.
-- Es idempotente para el lote con código LOTE-DEMO-001.
BEGIN;

DO $seed$
DECLARE
    demo_lote_id uuid;
    demo_muestra_id uuid;
    demo_diagnostico_id uuid;
    demo_proyecto_id uuid;
    demo_vivero_id uuid;
BEGIN
    SELECT id INTO demo_lote_id
    FROM public.lotes
    WHERE codigo = 'LOTE-DEMO-001'
    ORDER BY created_at
    LIMIT 1;

    IF demo_lote_id IS NULL THEN
        RAISE EXCEPTION 'No existe LOTE-DEMO-001. Crea primero la cuenca, subcuenca, predio y lote demo.';
    END IF;

    INSERT INTO public.lote_objetivos (lote_id, objetivo_id)
    SELECT demo_lote_id, id
    FROM public.objetivos_reforestacion
    WHERE codigo IN ('proteccion_hidrica', 'control_erosion', 'corredores_biologicos')
    ON CONFLICT DO NOTHING;

    SELECT id INTO demo_muestra_id
    FROM public.muestras_suelo
    WHERE lote_id = demo_lote_id AND ph = 6.2
    ORDER BY fecha_muestra DESC
    LIMIT 1;

    IF demo_muestra_id IS NULL THEN
        INSERT INTO public.muestras_suelo (
            lote_id, ph, textura_id, materia_organica_pct, humedad_retencion_pct
        )
        SELECT demo_lote_id, 6.2, t.id, 4.8, 58.0
        FROM public.texturas_suelo t
        WHERE t.codigo = 'franco'
        RETURNING id INTO demo_muestra_id;
    END IF;

    SELECT id INTO demo_diagnostico_id
    FROM public.diagnosticos_lote
    WHERE lote_id = demo_lote_id
      AND observaciones = 'Diagnóstico demostrativo de lote para pruebas locales.'
    ORDER BY fecha DESC
    LIMIT 1;

    IF demo_diagnostico_id IS NULL THEN
        INSERT INTO public.diagnosticos_lote (
            lote_id, muestra_suelo_id, zona_vida_id, regimen_precipitacion_id,
            precipitacion_anual_mm, perdida_cobertura_pct, franja_riparia_legal_m,
            riesgo_acarreo, conectividad_fauna, observaciones
        )
        SELECT
            demo_lote_id, demo_muestra_id, zv.id, rp.id,
            1510, 35.0, 30, 'medio', 'parcial',
            'Diagnóstico demostrativo de lote para pruebas locales.'
        FROM public.zonas_vida_holdridge zv
        CROSS JOIN public.regimenes_precipitacion rp
        WHERE zv.codigo = 'bmh-PM' AND rp.codigo = 'bimodal'
        RETURNING id INTO demo_diagnostico_id;
    END IF;

    INSERT INTO public.diagnostico_precipitacion_mensual (diagnostico_id, mes, precipitacion_mm)
    VALUES
        (demo_diagnostico_id, 1, 120), (demo_diagnostico_id, 2, 100),
        (demo_diagnostico_id, 3, 80),  (demo_diagnostico_id, 4, 70),
        (demo_diagnostico_id, 5, 100), (demo_diagnostico_id, 6, 180),
        (demo_diagnostico_id, 7, 220), (demo_diagnostico_id, 8, 200),
        (demo_diagnostico_id, 9, 130), (demo_diagnostico_id, 10, 100),
        (demo_diagnostico_id, 11, 90), (demo_diagnostico_id, 12, 120)
    ON CONFLICT (diagnostico_id, mes) DO UPDATE
        SET precipitacion_mm = EXCLUDED.precipitacion_mm;

    DELETE FROM public.ventanas_siembra WHERE diagnostico_id = demo_diagnostico_id;
    INSERT INTO public.ventanas_siembra (diagnostico_id, mes_inicio, mes_fin, nota)
    VALUES
        (demo_diagnostico_id, 6, 9, 'Ventana húmeda demostrativa; confirmar con datos locales.'),
        (demo_diagnostico_id, 12, 2, 'Ventana secundaria demostrativa; cruza diciembre-enero.');

    INSERT INTO public.diagnostico_especies (diagnostico_id, especie_id, compatibilidad_pct)
    SELECT demo_diagnostico_id, e.id,
           CASE e.codigo_taxon
               WHEN 'REF-114' THEN 91.0
               WHEN 'REF-187' THEN 84.0
               WHEN 'REF-208' THEN 78.0
               WHEN 'REF-305' THEN 73.0
               ELSE 68.0
           END
    FROM public.especies e
    WHERE e.codigo_taxon IN ('REF-114', 'REF-187', 'REF-208', 'REF-305')
    ON CONFLICT (diagnostico_id, especie_id) DO UPDATE
        SET compatibilidad_pct = EXCLUDED.compatibilidad_pct,
            calculado_en = now();

    IF NOT EXISTS (
        SELECT 1 FROM public.zonas_mapa
        WHERE lote_id = demo_lote_id AND etiqueta = 'Zona de siembra demo'
    ) THEN
        INSERT INTO public.zonas_mapa (lote_id, tipo, etiqueta, geom)
        SELECT demo_lote_id, 'siembra_prioritaria', 'Zona de siembra demo',
               extensions.ST_SetSRID(extensions.ST_GeomFromText(
                   'POLYGON((-75.254 4.404, -75.251 4.404, -75.251 4.401, -75.254 4.401, -75.254 4.404))'
               ), 4326);
    END IF;

    INSERT INTO public.viveros (nombre, municipio, ubicacion)
    VALUES (
        'Vivero Demo Reforestación',
        'Ibagué',
        extensions.ST_SetSRID(extensions.ST_MakePoint(-75.25, 4.40), 4326)
    )
    ON CONFLICT (nombre) DO NOTHING;

    SELECT id INTO demo_vivero_id
    FROM public.viveros
    WHERE nombre = 'Vivero Demo Reforestación';

    INSERT INTO public.vivero_stock (vivero_id, especie_id, stock)
    SELECT demo_vivero_id, e.id, 500
    FROM public.especies e
    WHERE e.codigo_taxon IN ('REF-114', 'REF-187', 'REF-208', 'REF-305')
    ON CONFLICT (vivero_id, especie_id) DO UPDATE SET stock = EXCLUDED.stock;

    SELECT id INTO demo_proyecto_id
    FROM public.proyectos
    WHERE lote_id = demo_lote_id AND nombre = 'Proyecto Demo de Restauración'
    LIMIT 1;

    IF demo_proyecto_id IS NULL THEN
        INSERT INTO public.proyectos (
            lote_id, diagnostico_id, vivero_id, nombre, fase,
            area_restaurada_m2, patron, espaciado_m
        )
        VALUES (
            demo_lote_id, demo_diagnostico_id, demo_vivero_id,
            'Proyecto Demo de Restauración', 'borrador',
            5000, 'tresbolillo', 3.0
        )
        RETURNING id INTO demo_proyecto_id;
    ELSE
        UPDATE public.proyectos
        SET diagnostico_id = demo_diagnostico_id, vivero_id = demo_vivero_id,
            area_restaurada_m2 = 5000, patron = 'tresbolillo', espaciado_m = 3.0
        WHERE id = demo_proyecto_id;
    END IF;

    INSERT INTO public.proyecto_especies (proyecto_id, especie_id, zona_plantacion_id, cantidad)
    SELECT demo_proyecto_id, e.id, z.id,
           CASE z.codigo WHEN 'dosel_alto' THEN 120 WHEN 'ripario' THEN 100 ELSE 80 END
    FROM public.especies e
    CROSS JOIN public.zonas_plantacion z
    WHERE (e.codigo_taxon = 'REF-114' AND z.codigo = 'dosel_alto')
       OR (e.codigo_taxon = 'REF-187' AND z.codigo = 'ripario')
       OR (e.codigo_taxon = 'REF-305' AND z.codigo = 'borde')
    ON CONFLICT (proyecto_id, especie_id, zona_plantacion_id) DO UPDATE
        SET cantidad = EXCLUDED.cantidad;

    INSERT INTO public.proyecto_insumos (
        proyecto_id, insumo_id, cantidad, precio_unitario_usd
    )
    SELECT
        demo_proyecto_id,
        ci.id,
        CASE
            WHEN lower(ci.unidad_dosis) = lower(ci.unidad_medida)
                THEN round(ci.dosis_por_hoyo * 300, 2)
            WHEN lower(ci.unidad_dosis) = 'kg'
                 AND lower(ci.unidad_medida) = 'bulto'
                 AND ci.presentacion ~* '25[[:space:]]*kg'
                THEN ceil(ci.dosis_por_hoyo * 300 / 25.0)
            ELSE ci.dosis_por_hoyo * 300
        END,
        ci.precio_referencia_usd
    FROM public.catalogo_insumos ci
    WHERE ci.precio_referencia_usd IS NOT NULL
    ON CONFLICT (proyecto_id, insumo_id) DO UPDATE
        SET cantidad = EXCLUDED.cantidad;
END
$seed$;

COMMIT;

SELECT l.id AS lote_id, l.codigo, l.nombre,
       d.id AS diagnostico_id, p.id AS proyecto_id,
       m.id AS muestra_suelo_id
FROM public.lotes l
LEFT JOIN public.diagnosticos_lote d
    ON d.lote_id = l.id
   AND d.observaciones = 'Diagnóstico demostrativo de lote para pruebas locales.'
LEFT JOIN public.proyectos p
    ON p.lote_id = l.id
   AND p.nombre = 'Proyecto Demo de Restauración'
LEFT JOIN public.muestras_suelo m
    ON m.lote_id = l.id
   AND m.ph = 6.2
WHERE l.codigo = 'LOTE-DEMO-001';
