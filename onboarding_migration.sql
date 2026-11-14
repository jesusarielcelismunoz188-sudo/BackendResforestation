-- Additive migration for databases created before onboarding support.
alter table public.predios
  add column if not exists municipio text,
  add column if not exists departamento text,
  add column if not exists area_ha numeric(10,2) check (area_ha > 0);

alter table public.cuencas
  add column if not exists es_espacio_personal boolean not null default false;

create index if not exists predios_created_by_idx
  on public.predios (created_by);
