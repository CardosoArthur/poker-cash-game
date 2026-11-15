-- Tabela para a sincronização opcional das sessões (poker/nuvem.py).
-- Rode no SQL Editor do seu projeto Supabase.

create table if not exists public.sessoes_poker (
    id bigint generated always as identity primary key,
    dispositivo text not null,
    id_local integer not null,
    inicio timestamp not null,
    fim timestamp,
    origem text not null default 'cash',
    config jsonb not null default '{}'::jsonb,
    big_blind integer not null,
    comprado integer not null,
    saida integer,
    maos integer not null,
    resultado integer not null,
    bb100 double precision,
    vpip double precision,
    pfr double precision,
    tres_bet double precision,
    wtsd double precision,
    wsd double precision,
    af double precision,
    atualizado_em timestamptz not null default now(),
    unique (dispositivo, id_local)
);

-- RLS ligado e nenhuma política para anon/authenticated: só a chave secreta
-- (service role), guardada localmente em dados/nuvem.json, consegue gravar e ler.
alter table public.sessoes_poker enable row level security;
