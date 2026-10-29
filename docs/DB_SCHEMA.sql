\restrict jVDp5M0z0eda2HaaozuKQuqvfPuXLdALHpu0QxnVKKsyOeVTxK8Pfcokw2OcAOg
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';
CREATE TABLE public.corrections (
    id bigint NOT NULL,
    document_id character varying(36) NOT NULL,
    field character varying(64) NOT NULL,
    old_value text,
    new_value text,
    note text,
    created_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.corrections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.corrections_id_seq OWNED BY public.corrections.id;
CREATE TABLE public.documents (
    id character varying(36) NOT NULL,
    filename character varying(255) NOT NULL,
    file_hash character varying(64) NOT NULL,
    kind character varying(16),
    size_bytes bigint NOT NULL,
    storage_path character varying(512) NOT NULL,
    status character varying(16) NOT NULL,
    error_code character varying(64),
    error_message text,
    page_count integer,
    pages_done integer NOT NULL,
    attempts integer NOT NULL,
    warnings jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone
);
CREATE TABLE public.extractions (
    id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    data jsonb NOT NULL,
    corrected jsonb,
    validation jsonb,
    needs_review boolean NOT NULL,
    supplier_name character varying(255),
    supplier_key character varying(255),
    invoice_number character varying(128),
    invoice_key character varying(128),
    invoice_date character varying(10),
    total numeric(18,4),
    currency character varying(3),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE TABLE public.pages (
    id bigint NOT NULL,
    document_id character varying(36) NOT NULL,
    page_no integer NOT NULL,
    label character varying(255),
    method character varying(16) NOT NULL,
    confidence double precision,
    text text NOT NULL,
    error text,
    duration_ms integer NOT NULL,
    embedding public.vector(1536)
);
CREATE SEQUENCE public.pages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.pages_id_seq OWNED BY public.pages.id;
CREATE TABLE public.processing_events (
    id bigint NOT NULL,
    document_id character varying(36) NOT NULL,
    stage character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    detail text,
    duration_ms integer,
    created_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.processing_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.processing_events_id_seq OWNED BY public.processing_events.id;
CREATE TABLE public.validation_issues (
    id bigint NOT NULL,
    document_id character varying(36) NOT NULL,
    rule character varying(64) NOT NULL,
    severity character varying(8) NOT NULL,
    field character varying(64),
    message text NOT NULL,
    details jsonb NOT NULL
);
CREATE SEQUENCE public.validation_issues_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.validation_issues_id_seq OWNED BY public.validation_issues.id;
ALTER TABLE ONLY public.corrections ALTER COLUMN id SET DEFAULT nextval('public.corrections_id_seq'::regclass);
ALTER TABLE ONLY public.pages ALTER COLUMN id SET DEFAULT nextval('public.pages_id_seq'::regclass);
ALTER TABLE ONLY public.processing_events ALTER COLUMN id SET DEFAULT nextval('public.processing_events_id_seq'::regclass);
ALTER TABLE ONLY public.validation_issues ALTER COLUMN id SET DEFAULT nextval('public.validation_issues_id_seq'::regclass);
ALTER TABLE ONLY public.corrections
    ADD CONSTRAINT corrections_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.extractions
    ADD CONSTRAINT extractions_document_id_key UNIQUE (document_id);
ALTER TABLE ONLY public.extractions
    ADD CONSTRAINT extractions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.processing_events
    ADD CONSTRAINT processing_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.validation_issues
    ADD CONSTRAINT validation_issues_pkey PRIMARY KEY (id);
CREATE INDEX ix_corrections_document_id ON public.corrections USING btree (document_id);
CREATE INDEX ix_documents_created_at ON public.documents USING btree (created_at);
CREATE INDEX ix_documents_file_hash ON public.documents USING btree (file_hash);
CREATE INDEX ix_documents_status ON public.documents USING btree (status);
CREATE INDEX ix_extractions_invoice_date ON public.extractions USING btree (invoice_date);
CREATE INDEX ix_extractions_invoice_key ON public.extractions USING btree (invoice_key);
CREATE INDEX ix_extractions_supplier_key ON public.extractions USING btree (supplier_key);
CREATE INDEX ix_pages_document_id ON public.pages USING btree (document_id);
CREATE INDEX ix_pages_embedding ON public.pages USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');
CREATE INDEX ix_processing_events_document_id ON public.processing_events USING btree (document_id);
CREATE INDEX ix_validation_issues_document_id ON public.validation_issues USING btree (document_id);
CREATE INDEX ix_validation_issues_rule ON public.validation_issues USING btree (rule);
ALTER TABLE ONLY public.corrections
    ADD CONSTRAINT corrections_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.extractions
    ADD CONSTRAINT extractions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.processing_events
    ADD CONSTRAINT processing_events_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.validation_issues
    ADD CONSTRAINT validation_issues_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
\unrestrict jVDp5M0z0eda2HaaozuKQuqvfPuXLdALHpu0QxnVKKsyOeVTxK8Pfcokw2OcAOg
