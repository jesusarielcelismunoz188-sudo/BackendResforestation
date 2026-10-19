-- =====================================================================
-- REFOREST · Seedling Epilogue — Esquema PostgreSQL para Supabase
-- Normalizado hasta 5FN. Ejecutar completo en el SQL Editor (BD limpia).
-- =====================================================================

-- ---------- 0. EXTENSIONES ----------
create extension if not exists postgis with schema extensions;
create extension if not exists pg_trgm with schema extensions;

-- ---------- 1. TIPOS ENUM ----------
create type prioridad_nivel      as enum ('alta','media','baja');
create type nivel_riesgo         as enum ('bajo','medio','medio_alto','alto');
create type estado_conectividad  as enum ('continuo','parcial','interrumpido');
create type rol_cuenca           as enum ('admin','tecnico','coordinador','voluntario');
create type fase_proyecto        as enum ('borrador','diagnostico','planificacion_activa','ejecucion','finalizado','cancelado');
create type patron_siembra       as enum ('tresbolillo','cuadrado','rectangular');
create type estado_insumo        as enum ('pendiente','en_transito','en_bodega');
create type tipo_actividad       as enum ('marcacion_trazado','jornada_siembra','monitoreo_riego','mantenimiento','otro');
create type estado_actividad     as enum ('programado','realizado','cancelado');
create type estado_voluntario    as enum ('convocado','confirmado','declinado','asistio');
create type tipo_zona_mapa       as enum ('siembra_prioritaria','franja_riparia','corredor_biologico');
create type aptitud_clima        as enum ('ideal','aceptable','no_recomendable');
create type tipo_documento       as enum ('ficha_proyecto','presupuesto','ficha_tecnica_especie');

-- ---------- 2. CATÁLOGOS (3FN) ----------
create table regimenes_hidricos (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table regimenes_precipitacion (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table texturas_suelo (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table objetivos_reforestacion (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table estratos_forestales (            -- posición vertical (emergente, dosel...)
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table grupos_funcionales (             -- filtro del catálogo
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table tasas_crecimiento (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null,
  incremento_min_m_anio numeric(3,1), incremento_max_m_anio numeric(3,1));

create table tipos_raiz (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null, funcion text);

create table servicios_ecosistemicos (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table etiquetas_especie (              -- "Floración Melífera", "Alta sequía"...
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table zonas_plantacion (               -- dosel alto / ripario / borde
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null);

create table metricas_impacto (
  id smallint generated always as identity primary key,
  codigo text not null unique, nombre text not null, unidad text not null);

create table practicas_siembra (
  id smallint generated always as identity primary key,
  codigo text not null unique, titulo text not null,
  descripcion text, parametro_defecto text);

create table familias_botanicas (
  id integer generated always as identity primary key,
  nombre text not null unique);

create table zonas_vida_holdridge (
  id smallint generated always as identity primary key,
  codigo text not null unique,                -- 'bmh-PM'
  nombre text not null,
  descripcion_microclima text,
  recomendacion_siembra text);

-- ---------- 3. USUARIOS Y TERRITORIO ----------
create table perfiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nombre_completo text not null,
  cargo text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now());

create table cuencas (
  id uuid primary key default gen_random_uuid(),
  nombre text not null unique,
  descripcion text,
  elevacion_msnm integer,
  altitud_min_msnm integer,
  altitud_max_msnm integer,
  geom extensions.geometry(MultiPolygon,4326),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (altitud_max_msnm is null or altitud_min_msnm is null or altitud_max_msnm >= altitud_min_msnm));

create table cuenca_miembros (
  cuenca_id uuid not null references cuencas(id) on delete cascade,
  perfil_id uuid not null references perfiles(id) on delete cascade,
  rol rol_cuenca not null default 'tecnico',
  created_at timestamptz not null default now(),
  primary key (cuenca_id, perfil_id));

create table subcuencas (
  id uuid primary key default gen_random_uuid(),
  cuenca_id uuid not null references cuencas(id) on delete cascade,
  nombre text not null,
  sector_microcuenca text,
  geom extensions.geometry(MultiPolygon,4326),
  unique (cuenca_id, nombre));

create table predios (
  id uuid primary key default gen_random_uuid(),
  subcuenca_id uuid not null references subcuencas(id) on delete cascade,
  nombre text not null,
  descripcion text,
  altitud_msnm integer,
  ubicacion extensions.geometry(Point,4326),
  created_by uuid references perfiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (subcuenca_id, nombre));

create table lotes (
  id uuid primary key default gen_random_uuid(),
  predio_id uuid not null references predios(id) on delete cascade,
  codigo text not null,                       -- 'FL-04'
  nombre text,                                -- 'Bellavista'
  area_ha numeric(10,2) check (area_ha > 0),
  prioridad prioridad_nivel not null default 'media',
  altitud_msnm integer,
  pendiente_grados numeric(4,1) check (pendiente_grados between 0 and 90),
  ubicacion extensions.geometry(Point,4326),
  geom extensions.geometry(Polygon,4326),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (predio_id, codigo));

create table lote_objetivos (
  lote_id uuid not null references lotes(id) on delete cascade,
  objetivo_id smallint not null references objetivos_reforestacion(id),
  primary key (lote_id, objetivo_id));

create table zonas_mapa (
  id uuid primary key default gen_random_uuid(),
  lote_id uuid not null references lotes(id) on delete cascade,
  tipo tipo_zona_mapa not null,
  etiqueta text,
  geom extensions.geometry(Geometry,4326) not null);

-- ---------- 4. DIAGNÓSTICO ----------
create table muestras_suelo (
  id uuid primary key default gen_random_uuid(),
  lote_id uuid not null references lotes(id) on delete cascade,
  fecha_muestra timestamptz not null default now(),
  ph numeric(3,1) not null check (ph between 0 and 14),
  textura_id smallint references texturas_suelo(id),
  materia_organica_pct numeric(4,1) check (materia_organica_pct between 0 and 100),
  humedad_retencion_pct numeric(4,1) check (humedad_retencion_pct between 0 and 100),
  tomada_por uuid references perfiles(id));

create table diagnosticos_lote (
  id uuid primary key default gen_random_uuid(),
  lote_id uuid not null references lotes(id) on delete cascade,
  muestra_suelo_id uuid references muestras_suelo(id),
  zona_vida_id smallint references zonas_vida_holdridge(id),
  regimen_precipitacion_id smallint references regimenes_precipitacion(id),
  precipitacion_anual_mm integer check (precipitacion_anual_mm >= 0),
  perdida_cobertura_pct numeric(4,1) check (perdida_cobertura_pct between 0 and 100),
  franja_riparia_legal_m smallint check (franja_riparia_legal_m >= 0),
  riesgo_acarreo nivel_riesgo,
  conectividad_fauna estado_conectividad,
  observaciones text,
  fecha timestamptz not null default now(),
  creado_por uuid references perfiles(id));

create table diagnostico_precipitacion_mensual (
  diagnostico_id uuid not null references diagnosticos_lote(id) on delete cascade,
  mes smallint not null check (mes between 1 and 12),
  precipitacion_mm numeric(6,1) not null check (precipitacion_mm >= 0),
  primary key (diagnostico_id, mes));

create table ventanas_siembra (
  id uuid primary key default gen_random_uuid(),
  diagnostico_id uuid not null references diagnosticos_lote(id) on delete cascade,
  mes_inicio smallint not null check (mes_inicio between 1 and 12),
  mes_fin smallint not null check (mes_fin between 1 and 12),
  nota text);

-- ---------- 5. ESPECIES ----------
create table especies (
  id uuid primary key default gen_random_uuid(),
  codigo_taxon text not null unique,          -- 'REF-208'
  nombre_comun text not null,
  nombre_cientifico text not null unique,
  familia_id integer references familias_botanicas(id),
  estrato_id smallint references estratos_forestales(id),
  grupo_funcional_id smallint references grupos_funcionales(id),
  tasa_crecimiento_id smallint references tasas_crecimiento(id),
  tipo_raiz_id smallint references tipos_raiz(id),
  descripcion_corta text,
  descripcion text,
  region_origen text,
  es_nativa boolean not null default true,
  prioridad_conservacion boolean not null default false,
  es_caducifolio boolean not null default false,
  altura_adulta_min_m numeric(5,1),
  altura_adulta_max_m numeric(5,1),
  espaciado_m numeric(4,1) check (espaciado_m > 0),
  longevidad_anios integer,
  epoca_optima text,
  altitud_min_msnm integer,
  altitud_max_msnm integer,
  ph_min numeric(3,1), ph_max numeric(3,1),
  humedad_radicular_min_pct numeric(4,1), humedad_radicular_max_pct numeric(4,1),
  horas_sol_min numeric(3,1),
  captura_co2_kg_anio numeric(6,1),
  compost_kg_hoyo numeric(4,2) not null default 3,
  roca_fosforica_g integer not null default 150,
  agua_inicial_l_planta numeric(4,1) not null default 12,
  plantulas_por_jornal integer not null default 20 check (plantulas_por_jornal > 0),
  imagen_url text,
  ficha_tecnica_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (altura_adulta_max_m is null or altura_adulta_min_m is null or altura_adulta_max_m >= altura_adulta_min_m),
  check (altitud_max_msnm is null or altitud_min_msnm is null or altitud_max_msnm >= altitud_min_msnm),
  check (ph_max is null or ph_min is null or ph_max >= ph_min));

create table especie_regimenes_hidricos (
  especie_id uuid not null references especies(id) on delete cascade,
  regimen_hidrico_id smallint not null references regimenes_hidricos(id),
  primary key (especie_id, regimen_hidrico_id));

create table especie_texturas (
  especie_id uuid not null references especies(id) on delete cascade,
  textura_id smallint not null references texturas_suelo(id),
  primary key (especie_id, textura_id));

create table especie_servicios (
  especie_id uuid not null references especies(id) on delete cascade,
  servicio_id smallint not null references servicios_ecosistemicos(id),
  descripcion text,
  metrica_valor numeric(8,2),
  metrica_unidad text,
  primary key (especie_id, servicio_id));

create table especie_etiquetas (
  especie_id uuid not null references especies(id) on delete cascade,
  etiqueta_id smallint not null references etiquetas_especie(id),
  primary key (especie_id, etiqueta_id));

create table protocolo_fases (
  id uuid primary key default gen_random_uuid(),
  especie_id uuid not null references especies(id) on delete cascade,
  orden smallint not null check (orden > 0),
  titulo text not null,
  descripcion text not null,
  parametro_etiqueta text,                    -- 'Riego'
  parametro_valor text,                       -- '12 litros'
  advertencia text,
  unique (especie_id, orden));

create table diagnostico_especies (           -- resultado del algoritmo
  diagnostico_id uuid not null references diagnosticos_lote(id) on delete cascade,
  especie_id uuid not null references especies(id) on delete cascade,
  compatibilidad_pct numeric(4,1) not null check (compatibilidad_pct between 0 and 100),
  calculado_en timestamptz not null default now(),
  primary key (diagnostico_id, especie_id));

-- ---------- 6. VIVERO ----------
create table viveros (
  id uuid primary key default gen_random_uuid(),
  nombre text not null unique,
  municipio text,
  ubicacion extensions.geometry(Point,4326));

create table vivero_stock (
  vivero_id uuid not null references viveros(id) on delete cascade,
  especie_id uuid not null references especies(id) on delete cascade,
  stock integer not null default 0 check (stock >= 0),
  certificado_origen_url text,
  actualizado_en timestamptz not null default now(),
  primary key (vivero_id, especie_id));

-- ---------- 7. PROYECTO / PLANIFICADOR ----------
create table proyectos (
  id uuid primary key default gen_random_uuid(),
  lote_id uuid not null references lotes(id) on delete cascade,
  diagnostico_id uuid references diagnosticos_lote(id),
  vivero_id uuid references viveros(id),
  responsable_id uuid references perfiles(id),
  nombre text not null,
  fase fase_proyecto not null default 'borrador',
  area_restaurada_m2 numeric(10,1) check (area_restaurada_m2 > 0),
  patron patron_siembra not null default 'tresbolillo',
  espaciado_m numeric(3,1) check (espaciado_m > 0),
  hoyo_lado_cm smallint not null default 40,
  hoyo_profundidad_cm smallint not null default 40,
  fecha_inicio date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now());

create table proyecto_especies (              -- ternaria: NO descomponible (5FN)
  proyecto_id uuid not null references proyectos(id) on delete cascade,
  especie_id uuid not null references especies(id),
  zona_plantacion_id smallint not null references zonas_plantacion(id),
  cantidad integer not null check (cantidad > 0),
  primary key (proyecto_id, especie_id, zona_plantacion_id));

create table proyecto_metricas (
  proyecto_id uuid not null references proyectos(id) on delete cascade,
  metrica_id smallint not null references metricas_impacto(id),
  valor numeric(12,2) not null,
  metodologia text,
  calculado_en timestamptz not null default now(),
  primary key (proyecto_id, metrica_id));

create table catalogo_insumos (
  id integer generated always as identity primary key,
  nombre text not null unique,
  descripcion text,
  presentacion text,                          -- 'Bulto 25 kg'
  unidad_medida text not null,
  dosis_por_hoyo numeric(8,3),
  unidad_dosis text,
  precio_referencia_usd numeric(10,2) check (precio_referencia_usd >= 0));

create table proyecto_insumos (
  proyecto_id uuid not null references proyectos(id) on delete cascade,
  insumo_id integer not null references catalogo_insumos(id),
  cantidad numeric(10,2) not null check (cantidad > 0),
  precio_unitario_usd numeric(10,2) not null check (precio_unitario_usd >= 0), -- precio histórico
  estado estado_insumo not null default 'pendiente',
  ubicacion text,
  fecha_estimada_llegada date,
  primary key (proyecto_id, insumo_id));

create table proyecto_practicas (
  proyecto_id uuid not null references proyectos(id) on delete cascade,
  practica_id smallint not null references practicas_siembra(id),
  valor_parametro text,
  primary key (proyecto_id, practica_id));

create table proyecto_actividades (
  id uuid primary key default gen_random_uuid(),
  proyecto_id uuid not null references proyectos(id) on delete cascade,
  semana smallint check (semana > 0),
  tipo tipo_actividad not null default 'otro',
  titulo text not null,
  descripcion text,
  fecha_programada timestamptz,
  estado estado_actividad not null default 'programado',
  realizada_en timestamptz,
  updated_at timestamptz not null default now());

create table voluntarios (
  id uuid primary key default gen_random_uuid(),
  perfil_id uuid unique references perfiles(id) on delete set null,
  nombre text not null,
  email text,
  telefono text,
  created_by uuid references perfiles(id) default auth.uid(),
  created_at timestamptz not null default now());

create table actividad_voluntarios (
  actividad_id uuid not null references proyecto_actividades(id) on delete cascade,
  voluntario_id uuid not null references voluntarios(id) on delete cascade,
  estado estado_voluntario not null default 'convocado',
  invitado_en timestamptz not null default now(),
  confirmado_en timestamptz,
  primary key (actividad_id, voluntario_id));

create table pronosticos_clima (
  id uuid primary key default gen_random_uuid(),
  lote_id uuid not null references lotes(id) on delete cascade,
  fecha date not null,
  resumen text,
  probabilidad_lluvia_pct smallint check (probabilidad_lluvia_pct between 0 and 100),
  aptitud aptitud_clima,
  unique (lote_id, fecha));

-- ---------- 8. TRANSVERSALES ----------
create table notificaciones (
  id uuid primary key default gen_random_uuid(),
  perfil_id uuid not null references perfiles(id) on delete cascade,
  tipo text not null,
  titulo text not null,
  mensaje text,
  proyecto_id uuid references proyectos(id) on delete cascade,
  leida boolean not null default false,
  created_at timestamptz not null default now());

create table documentos_exportados (
  id uuid primary key default gen_random_uuid(),
  proyecto_id uuid references proyectos(id) on delete cascade,
  especie_id uuid references especies(id) on delete cascade,
  tipo tipo_documento not null,
  url text not null,
  generado_por uuid references perfiles(id) default auth.uid(),
  created_at timestamptz not null default now(),
  check (proyecto_id is not null or especie_id is not null));

-- ---------- 9. ÍNDICES ----------
create index on cuenca_miembros (perfil_id);
create index on subcuencas (cuenca_id);
create index on predios (subcuenca_id);
create index on lotes (predio_id);
create index on lote_objetivos (objetivo_id);
create index on zonas_mapa (lote_id);
create index on muestras_suelo (lote_id, fecha_muestra desc);
create index on diagnosticos_lote (lote_id, fecha desc);
create index on diagnostico_especies (especie_id);
create index on especies (grupo_funcional_id);
create index on especies (estrato_id);
create index on especie_servicios (servicio_id);
create index on especie_etiquetas (etiqueta_id);
create index on vivero_stock (especie_id);
create index on proyectos (lote_id);
create index on proyecto_especies (especie_id);
create index on proyecto_insumos (insumo_id);
create index on proyecto_actividades (proyecto_id, fecha_programada);
create index on actividad_voluntarios (voluntario_id);
create index on notificaciones (perfil_id, leida);
create index on lotes using gist (geom);
create index on zonas_mapa using gist (geom);
create index on cuencas using gist (geom);
create index especies_nombre_comun_trgm on especies using gin (nombre_comun extensions.gin_trgm_ops);
create index especies_nombre_cient_trgm on especies using gin (nombre_cientifico extensions.gin_trgm_ops);

-- ---------- 10. VISTAS (valores derivados, no almacenados) ----------
create view v_diagnostico_vigente with (security_invoker = true) as
select distinct on (d.lote_id) d.*
from diagnosticos_lote d
order by d.lote_id, d.fecha desc;

create view v_diagnostico_resumen with (security_invoker = true) as
select d.id as diagnostico_id, d.lote_id,
       100 - d.perdida_cobertura_pct as cobertura_remanente_pct,
       count(ds.especie_id)          as total_especies_sugeridas,
       round(avg(ds.compatibilidad_pct), 1) as compatibilidad_promedio_pct
from diagnosticos_lote d
left join diagnostico_especies ds on ds.diagnostico_id = d.id
group by d.id;

create view v_especies_sugeridas with (security_invoker = true) as
select v.lote_id, v.id as diagnostico_id, e.id as especie_id, e.codigo_taxon,
       e.nombre_comun, e.nombre_cientifico, g.nombre as grupo_funcional,
       ds.compatibilidad_pct
from v_diagnostico_vigente v
join diagnostico_especies ds on ds.diagnostico_id = v.id
join especies e on e.id = ds.especie_id
left join grupos_funcionales g on g.id = e.grupo_funcional_id;

create view v_proyecto_resumen with (security_invoker = true) as
select p.id as proyecto_id, p.nombre, p.fase,
       coalesce(e.total_arboles, 0) as total_arboles,
       p.area_restaurada_m2,
       round(p.area_restaurada_m2 / 10000.0, 2) as area_ha,
       case when p.area_restaurada_m2 > 0
            then round(coalesce(e.total_arboles,0) / (p.area_restaurada_m2 / 10000.0))
       end as densidad_arboles_ha,
       coalesce(i.presupuesto_usd, 0) as presupuesto_insumos_usd,
       coalesce(i.total_insumos, 0)   as total_insumos,
       coalesce(i.insumos_en_bodega, 0) as insumos_en_bodega,
       round(coalesce(c.co2_kg_anio, 0) / 1000.0, 2) as captura_co2_ton_anio
from proyectos p
left join (select proyecto_id, sum(cantidad) as total_arboles
           from proyecto_especies group by proyecto_id) e on e.proyecto_id = p.id
left join (select proyecto_id,
                  sum(cantidad * precio_unitario_usd) as presupuesto_usd,
                  count(*) as total_insumos,
                  count(*) filter (where estado = 'en_bodega') as insumos_en_bodega
           from proyecto_insumos group by proyecto_id) i on i.proyecto_id = p.id
left join (select pe.proyecto_id, sum(pe.cantidad * es.captura_co2_kg_anio) as co2_kg_anio
           from proyecto_especies pe join especies es on es.id = pe.especie_id
           group by pe.proyecto_id) c on c.proyecto_id = p.id;

create view v_mezcla_botanica with (security_invoker = true) as
select pe.proyecto_id, z.codigo as zona, z.nombre as zona_nombre,
       sum(pe.cantidad) as unidades,
       round(100.0 * sum(pe.cantidad) / sum(sum(pe.cantidad)) over (partition by pe.proyecto_id), 1) as porcentaje
from proyecto_especies pe
join zonas_plantacion z on z.id = pe.zona_plantacion_id
group by pe.proyecto_id, z.codigo, z.nombre;

create view v_plan_siembra_calculo with (security_invoker = true) as
select pe.proyecto_id, pe.especie_id, e.nombre_comun,
       sum(pe.cantidad) as plantulas,
       round(sum(pe.cantidad) * e.compost_kg_hoyo, 1)         as compost_kg,
       round(sum(pe.cantidad) * e.agua_inicial_l_planta, 1)   as agua_inicial_l,
       round(sum(pe.cantidad)::numeric / e.plantulas_por_jornal, 1) as jornales,
       round(sum(pe.cantidad) * e.espaciado_m * e.espaciado_m, 0)   as area_aprox_m2
from proyecto_especies pe
join especies e on e.id = pe.especie_id
group by pe.proyecto_id, pe.especie_id, e.nombre_comun, e.compost_kg_hoyo,
         e.agua_inicial_l_planta, e.plantulas_por_jornal, e.espaciado_m;

create view v_actividad_voluntarios_resumen with (security_invoker = true) as
select actividad_id,
       count(*) filter (where estado in ('convocado','confirmado','asistio')) as convocados,
       count(*) filter (where estado in ('confirmado','asistio')) as confirmados
from actividad_voluntarios group by actividad_id;

-- ---------- 11. FUNCIONES Y TRIGGERS ----------
create function set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

do $$
declare t text;
begin
  foreach t in array array['perfiles','cuencas','predios','lotes','especies','proyectos','proyecto_actividades'] loop
    execute format('create trigger trg_%1$s_updated before update on public.%1$I
                    for each row execute function public.set_updated_at()', t);
  end loop;
end $$;

create function handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.perfiles (id, nombre_completo, avatar_url)
  values (new.id,
          coalesce(new.raw_user_meta_data->>'full_name', new.email, 'Sin nombre'),
          new.raw_user_meta_data->>'avatar_url')
  on conflict (id) do nothing;
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
for each row execute function public.handle_new_user();

create function agregar_creador_cuenca() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is not null then
    insert into public.cuenca_miembros (cuenca_id, perfil_id, rol)
    values (new.id, auth.uid(), 'admin') on conflict do nothing;
  end if;
  return new;
end $$;

create trigger trg_cuenca_creador after insert on cuencas
for each row execute function public.agregar_creador_cuenca();

-- Helpers de pertenencia (SECURITY DEFINER para evitar recursión en RLS)
create function es_miembro_cuenca(p_cuenca uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.cuenca_miembros m
                 where m.cuenca_id = p_cuenca and m.perfil_id = auth.uid()) $$;

create function es_admin_cuenca(p_cuenca uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.cuenca_miembros m
                 where m.cuenca_id = p_cuenca and m.perfil_id = auth.uid() and m.rol = 'admin') $$;

create function cuenca_de_subcuenca(p_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select s.cuenca_id from public.subcuencas s where s.id = p_id $$;

create function cuenca_de_predio(p_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select s.cuenca_id from public.predios p
  join public.subcuencas s on s.id = p.subcuenca_id where p.id = p_id $$;

create function cuenca_de_lote(p_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select s.cuenca_id from public.lotes l
  join public.predios p on p.id = l.predio_id
  join public.subcuencas s on s.id = p.subcuenca_id where l.id = p_id $$;

create function cuenca_de_diagnostico(p_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select public.cuenca_de_lote(d.lote_id) from public.diagnosticos_lote d where d.id = p_id $$;

create function cuenca_de_proyecto(p_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select public.cuenca_de_lote(p.lote_id) from public.proyectos p where p.id = p_id $$;

create function cuenca_de_actividad(p_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select public.cuenca_de_proyecto(a.proyecto_id) from public.proyecto_actividades a where a.id = p_id $$;

grant execute on function es_miembro_cuenca(uuid), es_admin_cuenca(uuid),
  cuenca_de_subcuenca(uuid), cuenca_de_predio(uuid), cuenca_de_lote(uuid),
  cuenca_de_diagnostico(uuid), cuenca_de_proyecto(uuid), cuenca_de_actividad(uuid)
  to authenticated;

-- ---------- 12. ROW LEVEL SECURITY ----------
-- 12.1 Catálogos y especies: lectura para autenticados (escritura: service_role / panel)
do $$
declare t text;
begin
  foreach t in array array[
    'regimenes_hidricos','regimenes_precipitacion','texturas_suelo','objetivos_reforestacion',
    'estratos_forestales','grupos_funcionales','tasas_crecimiento','tipos_raiz',
    'servicios_ecosistemicos','etiquetas_especie','zonas_plantacion','metricas_impacto',
    'practicas_siembra','familias_botanicas','zonas_vida_holdridge','especies',
    'especie_regimenes_hidricos','especie_texturas','especie_servicios','especie_etiquetas',
    'protocolo_fases','viveros','vivero_stock','catalogo_insumos'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('create policy "lectura_autenticados" on public.%I for select to authenticated using (true)', t);
  end loop;
end $$;

-- 12.2 Tablas ligadas a una cuenca: acceso solo para miembros
do $$
declare r text; t text; e text;
begin
  foreach r in array array[
    'subcuencas|public.es_miembro_cuenca(cuenca_id)',
    'predios|public.es_miembro_cuenca(public.cuenca_de_subcuenca(subcuenca_id))',
    'lotes|public.es_miembro_cuenca(public.cuenca_de_predio(predio_id))',
    'lote_objetivos|public.es_miembro_cuenca(public.cuenca_de_lote(lote_id))',
    'zonas_mapa|public.es_miembro_cuenca(public.cuenca_de_lote(lote_id))',
    'muestras_suelo|public.es_miembro_cuenca(public.cuenca_de_lote(lote_id))',
    'diagnosticos_lote|public.es_miembro_cuenca(public.cuenca_de_lote(lote_id))',
    'pronosticos_clima|public.es_miembro_cuenca(public.cuenca_de_lote(lote_id))',
    'proyectos|public.es_miembro_cuenca(public.cuenca_de_lote(lote_id))',
    'diagnostico_precipitacion_mensual|public.es_miembro_cuenca(public.cuenca_de_diagnostico(diagnostico_id))',
    'ventanas_siembra|public.es_miembro_cuenca(public.cuenca_de_diagnostico(diagnostico_id))',
    'diagnostico_especies|public.es_miembro_cuenca(public.cuenca_de_diagnostico(diagnostico_id))',
    'proyecto_especies|public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id))',
    'proyecto_metricas|public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id))',
    'proyecto_insumos|public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id))',
    'proyecto_practicas|public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id))',
    'proyecto_actividades|public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id))',
    'actividad_voluntarios|public.es_miembro_cuenca(public.cuenca_de_actividad(actividad_id))'
  ] loop
    t := split_part(r, '|', 1); e := split_part(r, '|', 2);
    execute format('alter table public.%I enable row level security', t);
    execute format('create policy "acceso_miembros" on public.%I for all to authenticated using (%s) with check (%s)', t, e, e);
  end loop;
end $$;

-- 12.3 Políticas específicas
alter table perfiles enable row level security;
create policy "perfiles_lectura" on perfiles for select to authenticated using (true);
create policy "perfiles_update_propio" on perfiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

alter table cuencas enable row level security;
create policy "cuencas_select" on cuencas for select to authenticated using (public.es_miembro_cuenca(id));
create policy "cuencas_insert" on cuencas for insert to authenticated with check (true);
create policy "cuencas_update" on cuencas for update to authenticated
  using (public.es_admin_cuenca(id)) with check (public.es_admin_cuenca(id));
create policy "cuencas_delete" on cuencas for delete to authenticated using (public.es_admin_cuenca(id));

alter table cuenca_miembros enable row level security;
create policy "miembros_select" on cuenca_miembros for select to authenticated
  using (public.es_miembro_cuenca(cuenca_id));
create policy "miembros_admin" on cuenca_miembros for all to authenticated
  using (public.es_admin_cuenca(cuenca_id)) with check (public.es_admin_cuenca(cuenca_id));

alter table voluntarios enable row level security;
create policy "voluntarios_propios" on voluntarios for all to authenticated
  using (created_by = auth.uid() or perfil_id = auth.uid())
  with check (created_by = auth.uid() or perfil_id = auth.uid());

alter table notificaciones enable row level security;
create policy "notificaciones_propias" on notificaciones for all to authenticated
  using (perfil_id = auth.uid()) with check (perfil_id = auth.uid());

alter table documentos_exportados enable row level security;
create policy "documentos_miembros" on documentos_exportados for select to authenticated
  using (proyecto_id is null or public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id)));
create policy "documentos_insert" on documentos_exportados for insert to authenticated
  with check (proyecto_id is null or public.es_miembro_cuenca(public.cuenca_de_proyecto(proyecto_id)));

-- ---------- 13. DATOS SEMILLA ----------
insert into regimenes_hidricos (codigo, nombre) values
  ('seco','Seco'), ('moderado','Moderado'), ('humedo','Húmedo');

insert into regimenes_precipitacion (codigo, nombre) values
  ('monomodal','Monomodal'), ('bimodal','Bimodal');

insert into texturas_suelo (codigo, nombre) values
  ('franco','Franco'), ('franco_arcilloso','Franco-arcilloso'),
  ('franco_arenoso','Franco-arenoso'), ('arcillo_arenoso','Arcillo-arenoso'),
  ('arcilloso','Arcilloso'), ('arenoso','Arenoso');

insert into objetivos_reforestacion (codigo, nombre) values
  ('proteccion_hidrica','Protección Hídrica'), ('corredores_biologicos','Corredores Biológicos'),
  ('control_erosion','Control de Erosión'), ('madera_sombra','Madera Nativa y Sombra');

insert into estratos_forestales (codigo, nombre) values
  ('emergente','Emergente'), ('dosel','Dosel'), ('subdosel','Subdosel'), ('sotobosque','Sotobosque');

insert into grupos_funcionales (codigo, nombre) values
  ('dosel','Árboles de Dosel'), ('pionera','Pioneras Rápidas'),
  ('fijadora_n2','Fijadoras de N₂'), ('sotobosque_cerca','Sotobosque y Cercas');

insert into tasas_crecimiento (codigo, nombre, incremento_min_m_anio, incremento_max_m_anio) values
  ('rapido','Rápido (>1.5 m/año)', 1.5, null),
  ('medio','Medio (0.8 - 1.5 m/año)', 0.8, 1.5),
  ('lento','Lento / Clímax (<0.8 m/año)', null, 0.8);

insert into tipos_raiz (codigo, nombre, funcion) values
  ('pivotante','Pivotante profunda','Antideslaves'),
  ('fasciculada','Fasciculada densa','Control de erosión'),
  ('radicular_extendida','Radicular extendida','Estabilización superficial');

insert into servicios_ecosistemicos (codigo, nombre) values
  ('cosecha_agua','Cosecha de Agua'), ('fijacion_n2','Fijación N₂'),
  ('aves_fauna','Aves y Fauna'), ('captura_carbono','Captura Carbono'),
  ('polinizadores','Atracción de Polinizadores'), ('micorrizas','Acolchado y Micorrizas'),
  ('control_erosion','Control de Erosión');

insert into etiquetas_especie (codigo, nombre) values
  ('floracion_melifera','Floración Melífera'), ('crecimiento_medio','Crecimiento Medio'),
  ('alta_sequia','Alta sequía'), ('riberena','Ribereña'), ('simbiotica_frankia','Simbiótica Frankia'),
  ('refugio_avifauna','Refugio Avifauna'), ('cerca_viva','Cerca Viva'),
  ('aroma_citrico','Aroma Cítrico'), ('madera_preciosa','Madera Preciosa'),
  ('sombrio','Sombrío'), ('suelos_ricos','Suelos Ricos');

insert into zonas_plantacion (codigo, nombre) values
  ('dosel_alto','Dosel Alto'), ('ripario','Ripario'), ('borde','Borde');

insert into metricas_impacto (codigo, nombre, unidad) values
  ('captura_co2','Captura de CO₂','ton/año'),
  ('agua_infiltrada','Agua infiltrada (recarga)','%'),
  ('aporte_acuifero','Aporte al acuífero','m³/año');

insert into practicas_siembra (codigo, titulo, descripcion, parametro_defecto) values
  ('profundidad_raiz','Profundidad de Raíz','Cuello de la plántula alineado a 2 cm bajo el nivel del suelo circundante con microcuenca de captación.','2 cm'),
  ('mulch_natural','Mulch / Acolchado Natural','Capa protectora de hojarasca y ramas trituradas para prevenir desecación y malezas.','8 cm'),
  ('corredor_biologico','Corredor Biológico','Conecta el parche boscoso con el drenaje natural reduciendo la fragmentación.', null);

insert into familias_botanicas (nombre) values
  ('Bignoniaceae'), ('Betulaceae'), ('Fagaceae'), ('Myrtaceae'), ('Meliaceae'), ('Juglandaceae');

insert into zonas_vida_holdridge (codigo, nombre, descripcion_microclima, recomendacion_siembra) values
  ('bmh-PM','Bosque Premontano Húmedo',
   'Microclima con alta nubosidad matinal y saturación radicular intermitente.',
   'Priorizar especies pioneras fijadoras de nitrógeno y estratos de galería para estabilización de riberas fluviales.');

insert into catalogo_insumos (nombre, presentacion, unidad_medida, dosis_por_hoyo, unidad_dosis, precio_referencia_usd) values
  ('Compost Orgánico Maduro','Bulto 25 kg','bulto',3.75,'kg',8.00),
  ('Hidrogel Retenedor','Polímero biodegradable','kg',0.05,'kg',12.00),
  ('Tutores y Amarras','Vara de bambú 1.5 m + fibra yute','kit',1,'kit',0.60);

-- Especies de ejemplo (valores aproximados: validar con el equipo técnico)
insert into especies (codigo_taxon, nombre_comun, nombre_cientifico, familia_id, estrato_id,
  grupo_funcional_id, tasa_crecimiento_id, tipo_raiz_id, descripcion_corta,
  altura_adulta_min_m, altura_adulta_max_m, espaciado_m, longevidad_anios,
  altitud_min_msnm, altitud_max_msnm, ph_min, ph_max,
  humedad_radicular_min_pct, humedad_radicular_max_pct, horas_sol_min,
  captura_co2_kg_anio, epoca_optima)
select v.cod, v.comun, v.sci, f.id, e.id, g.id, t.id, r.id, v.corta,
       v.hmin, v.hmax, v.esp, v.longev, v.amin, v.amax, v.phmin, v.phmax,
       v.humin, v.humax, v.sol, v.co2, v.epoca
from (values
 ('REF-208','Guayacán Rosado','Handroanthus chrysanthus','Bignoniaceae','emergente','dosel','medio','pivotante','Árbol maderable y melífero primordial del Neotrópico.',15,22,5,100,1000,2200,5.8,6.8,45,60,6,28,'Lluvias'),
 ('REF-114','Aliso Andino','Alnus acuminata','Betulaceae','dosel','fijadora_n2','rapido','fasciculada','Fijador biológico de nitrógeno por excelencia, con raíces simbióticas.',20,25,4,80,1500,3200,5.0,7.0,50,75,5,22,'Lluvias'),
 ('REF-231','Roble de Montaña','Quercus costaricensis','Fagaceae','dosel','dosel','lento','pivotante','Pilar estructural del bosque maduro.',25,30,6,200,1800,3200,4.5,6.5,50,70,4,18,'Lluvias'),
 ('REF-305','Arrayán / Murta','Myrcianthes leucoxyla','Myrtaceae','sotobosque','sotobosque_cerca','medio','radicular_extendida','Especie compacta y melífera; sus frutos alimentan fauna.',6,8,2,60,1500,3000,5.5,7.0,40,65,4,9,'Lluvias'),
 ('REF-187','Cedro de Montaña','Cedrela montana','Meliaceae','dosel','dosel','medio','pivotante','Especie de altísimo valor biológico y fijadora de carbono.',25,28,6,100,1800,3000,5.5,7.0,45,65,5,24,'Lluvias'),
 ('REF-249','Nogal Silvestre','Juglans neotropica','Juglandaceae','dosel','dosel','medio','pivotante','Árbol noble de copa globosa y raíz pivotante profunda.',20,22,6,120,1800,3000,6.0,7.0,45,65,4,20,'Lluvias')
) as v(cod,comun,sci,familia,estrato,grupo,tasa,raiz,corta,hmin,hmax,esp,longev,amin,amax,phmin,phmax,humin,humax,sol,co2,epoca)
join familias_botanicas f on f.nombre = v.familia
join estratos_forestales e on e.codigo = v.estrato
join grupos_funcionales g on g.codigo = v.grupo
join tasas_crecimiento t on t.codigo = v.tasa
join tipos_raiz r on r.codigo = v.raiz;

-- Marcar atributos propios de la ficha del Guayacán
update especies set prioridad_conservacion = true, es_caducifolio = true where codigo_taxon = 'REF-208';
-- =====================================================================
-- FIN
-- =====================================================================
