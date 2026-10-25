-- Schema Supabase pentru verificarea facturilor fata de contracte.
-- Rulati o data in Supabase SQL Editor.

create table if not exists contracte (
  id                 bigint generated always as identity primary key,
  furnizor_cif       text not null,            -- normalizat: doar cifre, fara "RO"
  furnizor_nume      text,
  nr_contract        text,
  data_start         date,
  data_end           date,                     -- null = durata nedeterminata
  moneda             text not null default 'RON',
  plafon_valoare     numeric(18,2),            -- fara TVA, in moneda contractului
  termen_plata_zile  integer,
  cota_tva           numeric(5,2),
  pdf_path           text not null unique,     -- cale in bucket-ul "contracte"
  pdf_sha256         text not null,
  status             text not null check (status in ('clar','neclar')),
  detalii_neclare    jsonb not null default '[]'::jsonb,
  extras_la          timestamptz not null default now()
);
create index if not exists contracte_cif_idx on contracte (furnizor_cif);

create table if not exists contract_articole (
  id              bigint generated always as identity primary key,
  contract_id     bigint not null references contracte(id) on delete cascade,
  denumire        text not null,
  cod             text,
  um              text,
  pret_unitar     numeric(18,4) not null,      -- fara TVA
  moneda          text not null default 'RON',
  cantitate_max   numeric(18,3),               -- null = fara plafon de cantitate
  cont            text                         -- cont SAGA (ex. 6028, 628); null = contul implicit din config
);
-- Pentru o baza creata cu o versiune mai veche a acestui fisier:
alter table contract_articole add column if not exists cont text;
create index if not exists contract_articole_contract_idx on contract_articole (contract_id);

-- Corectii optionale facute de admin: denumirea de pe factura -> articolul din contract.
create table if not exists mapari_articole (
  id                   bigint generated always as identity primary key,
  furnizor_cif         text not null,
  denumire_factura     text not null,          -- normalizata (vezi matcher.normalize)
  contract_articol_id  bigint not null references contract_articole(id) on delete cascade,
  unique (furnizor_cif, denumire_factura)
);

create table if not exists facturi_procesate (
  id                  bigint generated always as identity primary key,
  furnizor_cif        text not null,
  nr                  text not null,
  data                date not null,
  valoare_fara_tva_ron numeric(18,2) not null,
  conform             boolean not null,
  mesaj               text not null,
  xml_original_path   text not null,
  saga_xml_path       text not null,
  procesat_la         timestamptz not null default now(),
  unique (furnizor_cif, nr, data)
);

-- Ce a consumat fiecare factura din fiecare contract (pentru plafoane cumulate).
create table if not exists facturi_procesate_linii (
  id                   bigint generated always as identity primary key,
  factura_id           bigint not null references facturi_procesate(id) on delete cascade,
  contract_id          bigint not null references contracte(id) on delete cascade,
  contract_articol_id  bigint references contract_articole(id) on delete set null,
  cantitate            numeric(18,3) not null,
  valoare_contract     numeric(18,2) not null  -- fara TVA, in moneda contractului
);
create index if not exists fpl_contract_idx on facturi_procesate_linii (contract_id);
create index if not exists fpl_articol_idx on facturi_procesate_linii (contract_articol_id);

create table if not exists curs_bnr (
  data    date not null,
  moneda  text not null,
  curs    numeric(12,6) not null,              -- RON pentru 1 unitate
  primary key (data, moneda)
);

-- Sume cumulate, citite de script inainte de fiecare verificare.
create or replace view consum_contracte as
  select contract_id, sum(valoare_contract) as valoare
  from facturi_procesate_linii group by contract_id;

create or replace view consum_articole as
  select contract_articol_id, sum(cantitate) as cantitate
  from facturi_procesate_linii where contract_articol_id is not null
  group by contract_articol_id;

-- Bucket privat pentru PDF-uri.
insert into storage.buckets (id, name, public)
values ('contracte', 'contracte', false)
on conflict (id) do nothing;

-- Scriptul foloseste service key; nimeni altcineva nu are acces.
alter table contracte enable row level security;
alter table contract_articole enable row level security;
alter table mapari_articole enable row level security;
alter table facturi_procesate enable row level security;
alter table facturi_procesate_linii enable row level security;
alter table curs_bnr enable row level security;
