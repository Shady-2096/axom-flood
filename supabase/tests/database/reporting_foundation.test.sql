begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(15);

select extensions.has_schema('reporting', 'private reporting schema exists');
select extensions.has_schema('api', 'narrow API schema exists');
select extensions.has_table('reporting', 'reports', 'reports table exists');
select extensions.has_table(
  'reporting',
  'conversation_sessions',
  'conversation sessions table exists'
);
select extensions.has_table(
  'reporting',
  'inbound_deliveries',
  'idempotency ledger exists'
);
select extensions.has_table(
  'reporting',
  'verification_events',
  'append-only verification events exist'
);
select extensions.has_index(
  'reporting',
  'reports',
  'reports_location_gix',
  'report location has a spatial index'
);
select extensions.has_index(
  'reporting',
  'geographies',
  'geographies_reviewed_boundary_gix',
  'reviewed boundaries have a partial spatial index'
);
select extensions.has_function(
  'api',
  'consume_rate_limit',
  array['text', 'text', 'timestamp with time zone', 'integer', 'timestamp with time zone'],
  'atomic rate-limit routine exists'
);
select extensions.has_function(
  'api',
  'start_or_get_conversation',
  array['text', 'text', 'date', 'smallint', 'smallint'],
  'conversation start routine exists'
);
select extensions.has_function(
  'api',
  'export_report_candidates',
  array['timestamp with time zone', 'timestamp with time zone'],
  'private export routine exists'
);
select extensions.table_privs_are(
  'reporting',
  'reports',
  'anon',
  array[]::text[],
  'anon has no report privileges'
);
select extensions.table_privs_are(
  'reporting',
  'reports',
  'authenticated',
  array[]::text[],
  'authenticated has no report privileges'
);
select extensions.table_privs_are(
  'reporting',
  'conversation_sessions',
  'anon',
  array[]::text[],
  'anon has no session privileges'
);
select extensions.table_privs_are(
  'reporting',
  'inbound_deliveries',
  'authenticated',
  array[]::text[],
  'authenticated has no delivery privileges'
);

select * from extensions.finish();
rollback;
