begin;

create table users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  created_at timestamptz not null default now(),
  status text not null default 'registered' check (status in ('registered','trial','subscriber'))
);
create table guests (
  fingerprint text primary key,
  messages_used int not null default 0,
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  ip_hash text
);
create table plans (
  id text primary key,
  name text not null,
  price_cents int not null,
  currency text not null default 'EUR',
  trial_days int not null default 0,
  ls_variant_id text,
  active boolean not null default true
);
create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  ls_subscription_id text,
  plan_id text references plans(id),
  status text not null,
  trial_ends_at timestamptz, renews_at timestamptz, cancelled_at timestamptz,
  created_at timestamptz not null default now()
);
create table limits (
  status text primary key,           -- guest|registered|trial|subscriber
  messages int not null,
  period text not null check (period in ('total','day'))
);
create table usage_daily (
  user_id uuid not null references users(id) on delete cascade,
  day date not null,
  messages int not null default 0,
  cost_cents numeric(10,4) not null default 0,
  primary key (user_id, day)
);
create table charlie_state (
  user_id uuid primary key references users(id) on delete cascade,
  mood text not null default 'calm',
  mood_level int not null default 3,
  attention int not null default 6,
  relationship text not null default 'new',
  last_call_at timestamptz,
  offended_reason text,
  updated_at timestamptz not null default now()
);
create table memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  kind text not null check (kind in ('fact','promise','topic','how_treated','name')),
  content text not null,
  created_at timestamptz not null default now()
);
create index memories_user_idx on memories(user_id, created_at desc);
create table day_events (
  id serial primary key,
  text text not null,
  mood_effect text not null,   -- calm|happy|angry|offended|sad|ashamed
  weight int not null default 1
);
create table user_day_event (
  user_id uuid not null references users(id) on delete cascade,
  day date not null,
  event_id int not null references day_events(id),
  primary key (user_id, day)
);
create table calls (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete set null,
  guest_fp text,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  duration_s int,
  start_mood text, end_mood text,
  summary text,
  praise text
);
create index calls_user_idx on calls(user_id, started_at desc);
create table messages (
  id uuid primary key default gen_random_uuid(),
  call_id uuid not null references calls(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  text text not null,
  emotion text,
  tokens_in int not null default 0, tokens_out int not null default 0,
  tts_chars int not null default 0, stt_sec numeric(8,2) not null default 0,
  cost_cents numeric(10,6) not null default 0,
  created_at timestamptz not null default now()
);
create index messages_call_idx on messages(call_id, created_at);
create table provider_rates (
  id serial primary key,
  provider text not null,
  unit text not null,          -- token_in|token_out|char|second
  price_per_unit numeric(14,10) not null,
  currency text not null default 'USD',
  effective_from date not null default current_date
);
create table fallback_phrases (
  id serial primary key,
  text text not null,
  emotion text not null default 'calm'
);

alter table users enable row level security;
alter table guests enable row level security;
alter table plans enable row level security;
alter table subscriptions enable row level security;
alter table limits enable row level security;
alter table usage_daily enable row level security;
alter table charlie_state enable row level security;
alter table memories enable row level security;
alter table day_events enable row level security;
alter table user_day_event enable row level security;
alter table calls enable row level security;
alter table messages enable row level security;
alter table provider_rates enable row level security;
alter table fallback_phrases enable row level security;

create policy users_select_own on users for select using (auth.uid() = id);
create policy subscriptions_select_own on subscriptions for select using (auth.uid() = user_id);
create policy usage_daily_select_own on usage_daily for select using (auth.uid() = user_id);
create policy charlie_state_select_own on charlie_state for select using (auth.uid() = user_id);
create policy memories_select_own on memories for select using (auth.uid() = user_id);
create policy user_day_event_select_own on user_day_event for select using (auth.uid() = user_id);
create policy calls_select_own on calls for select using (auth.uid() = user_id);
create policy messages_select_own on messages for select using (
  exists (select 1 from calls c where c.id = messages.call_id and c.user_id = auth.uid())
);
create policy plans_select_public on plans for select using (true);
create policy limits_select_public on limits for select using (true);
create policy day_events_select_public on day_events for select using (true);
create policy fallback_phrases_select_public on fallback_phrases for select using (true);

create view v_daily_margin as
select day, count(distinct user_id) as users, sum(messages) as messages, sum(cost_cents) as cost_cents
from usage_daily group by day order by day desc;

commit;
