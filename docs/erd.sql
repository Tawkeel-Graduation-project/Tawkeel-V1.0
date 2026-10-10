CREATE TABLE "users" (
  "id" uuid PRIMARY KEY,
  "full_name" varchar,
  "role" varchar NOT NULL,
  "email" varchar UNIQUE NOT NULL,
  "password_hash" varchar NOT NULL,
  "created_at" timestamp
);

CREATE TABLE "lawyer_profiles" (
  "id" uuid PRIMARY KEY,
  "user_id" uuid UNIQUE NOT NULL,
  "niches" varchar[],
  "city" varchar,
  "fee_min" integer,
  "fee_max" integer,
  "years_experience" integer,
  "bio" text,
  "verified" bool,
  "created_at" timestamp
);

CREATE TABLE "availability_slots" (
  "id" uuid PRIMARY KEY,
  "lawyer_id" uuid NOT NULL,
  "weekday" int,
  "start_time" time,
  "end_time" time
);

CREATE TABLE "availability_blocks" (
  "id" uuid PRIMARY KEY,
  "lawyer_id" uuid NOT NULL,
  "starts_at" timestamp,
  "ends_at" timestamp,
  "reason" varchar
);

CREATE TABLE "requests" (
  "id" uuid PRIMARY KEY,
  "client_id" uuid NOT NULL,
  "lawyer_id" uuid NOT NULL,
  "conversation_id" uuid,
  "niche" varchar,
  "summary" jsonb,
  "status" varchar,
  "decline_reason" text,
  "client_confirmed_at" timestamp,
  "created_at" timestamp
);

CREATE TABLE "cases" (
  "id" uuid PRIMARY KEY,
  "request_id" uuid UNIQUE NOT NULL,
  "lawyer_id" uuid NOT NULL,
  "status" varchar,
  "summary" jsonb,
  "notes" text,
  "created_at" timestamp,
  "updated_at" timestamp
);

CREATE TABLE "conversations" (
  "id" uuid PRIMARY KEY,
  "user_id" uuid NOT NULL,
  "type" varchar,
  "case_id" uuid,
  "created_at" timestamp
);

CREATE TABLE "messages" (
  "id" uuid PRIMARY KEY,
  "conversation_id" uuid NOT NULL,
  "sender" varchar,
  "content" text,
  "citations" jsonb,
  "created_at" timestamp
);

CREATE TABLE "documents" (
  "id" uuid PRIMARY KEY,
  "owner_id" uuid NOT NULL,
  "case_id" uuid,
  "type" varchar,
  "content" jsonb,
  "status" varchar,
  "created_at" timestamp
);

CREATE TABLE "meetings" (
  "id" uuid PRIMARY KEY,
  "request_id" uuid NOT NULL,
  "starts_at" timestamp,
  "ends_at" timestamp,
  "status" varchar
);

CREATE TABLE "workflows" (
  "id" uuid PRIMARY KEY,
  "case_id" uuid,
  "request_id" uuid,
  "kind" varchar,
  "status" varchar,
  "state" jsonb,
  "created_at" timestamp
);

CREATE TABLE "audit_events" (
  "id" uuid PRIMARY KEY,
  "actor_id" uuid NOT NULL,
  "case_id" uuid,
  "action" varchar,
  "before" jsonb,
  "after" jsonb,
  "created_at" timestamp
);

CREATE TABLE "consents" (
  "id" uuid PRIMARY KEY,
  "user_id" uuid NOT NULL,
  "request_id" uuid,
  "type" varchar,
  "document_version" varchar,
  "consented_at" timestamp
);

CREATE TABLE "notifications" (
  "id" uuid PRIMARY KEY,
  "user_id" uuid NOT NULL,
  "request_id" uuid,
  "type" varchar,
  "message" text,
  "is_read" bool,
  "created_at" timestamp
);

CREATE TABLE "legal_chunks" (
  "id" uuid PRIMARY KEY,
  "source_type" varchar,
  "source_name" varchar,
  "article_number" varchar,
  "source_date" date,
  "text" text,
  "url" varchar,
  "embedding" vector(1024)
);

ALTER TABLE "lawyer_profiles" ADD FOREIGN KEY ("user_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "availability_slots" ADD FOREIGN KEY ("lawyer_id") REFERENCES "lawyer_profiles" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "availability_blocks" ADD FOREIGN KEY ("lawyer_id") REFERENCES "lawyer_profiles" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "requests" ADD FOREIGN KEY ("client_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "requests" ADD FOREIGN KEY ("lawyer_id") REFERENCES "lawyer_profiles" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "requests" ADD FOREIGN KEY ("conversation_id") REFERENCES "conversations" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "cases" ADD FOREIGN KEY ("request_id") REFERENCES "requests" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "cases" ADD FOREIGN KEY ("lawyer_id") REFERENCES "lawyer_profiles" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "conversations" ADD FOREIGN KEY ("user_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "conversations" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "messages" ADD FOREIGN KEY ("conversation_id") REFERENCES "conversations" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "documents" ADD FOREIGN KEY ("owner_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "documents" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "meetings" ADD FOREIGN KEY ("request_id") REFERENCES "requests" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "workflows" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "workflows" ADD FOREIGN KEY ("request_id") REFERENCES "requests" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "audit_events" ADD FOREIGN KEY ("actor_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "audit_events" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "consents" ADD FOREIGN KEY ("user_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "consents" ADD FOREIGN KEY ("request_id") REFERENCES "requests" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "notifications" ADD FOREIGN KEY ("user_id") REFERENCES "users" ("id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "notifications" ADD FOREIGN KEY ("request_id") REFERENCES "requests" ("id") DEFERRABLE INITIALLY IMMEDIATE;
