--
-- PostgreSQL database dump
--

\restrict XaywYSYjFPbtejbuvHavRbNlkYpp79og4AkSepNNvpuRQDUhK5XoQnoWHDfhojy

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

-- Started on 2026-03-21 16:13:09

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 893 (class 1247 OID 16390)
-- Name: actiontype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.actiontype AS ENUM (
    'TICKET_CREATED',
    'TICKET_ASSIGNED',
    'TICKET_ESCALATED',
    'TICKET_CLOSED',
    'STATUS_CHANGED',
    'MESSAGE_SENT',
    'FILE_UPLOADED',
    'USER_REGISTERED',
    'KEY_CONFLICT_DETECTED',
    'api_retry_failed',
    'calendar_rule_created',
    'calendar_rule_deleted',
    'calendar_period_cleared',
    'CALENDAR_RULE_CREATED',
    'CALENDAR_RULE_DELETED',
    'CALENDAR_PERIOD_CLEARED',
    'STAFF_UPDATED',
    'STAFF_ADDED',
    'STAFF_DEACTIVATED',
    'STAFF_ACTIVATED',
    'BROADCAST_SENT',
    'setting_changed',
    'setting_reset',
    'SETTING_CHANGED',
    'SETTING_RESET',
    'reminder_sent',
    'escalated',
    'clients_transferred',
    'REMINDER_SENT',
    'ESCALATED',
    'CLIENTS_TRANSFERRED',
    'API_RETRY_FAILED',
    'phone_change_requested',
    'phone_change_approved',
    'phone_change_rejected',
    'PHONE_CHANGE_REQUESTED',
    'PHONE_CHANGE_APPROVED',
    'PHONE_CHANGE_REJECTED'
);


--
-- TOC entry 896 (class 1247 OID 16456)
-- Name: broadcaststatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.broadcaststatus AS ENUM (
    'DRAFT',
    'SENDING',
    'COMPLETED',
    'FAILED'
);


--
-- TOC entry 899 (class 1247 OID 16466)
-- Name: deliverymethod; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.deliverymethod AS ENUM (
    'TELEGRAM',
    'EMAIL',
    'NONE'
);


--
-- TOC entry 902 (class 1247 OID 16474)
-- Name: deliverystatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.deliverystatus AS ENUM (
    'PENDING',
    'DELIVERED',
    'FAILED'
);


--
-- TOC entry 905 (class 1247 OID 16482)
-- Name: escalationtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.escalationtype AS ENUM (
    'reminder_10min',
    'escalation_20min',
    'REMINDER_10MIN',
    'REMINDER_20MIN',
    'ESCALATION_20MIN'
);


--
-- TOC entry 908 (class 1247 OID 16494)
-- Name: eventstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventstatus AS ENUM (
    'SCHEDULED',
    'SENT',
    'FAILED',
    'CANCELLED'
);


--
-- TOC entry 911 (class 1247 OID 16504)
-- Name: eventtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventtype AS ENUM (
    'RENEWAL_REMINDER_30',
    'RENEWAL_REMINDER_7',
    'NPS_SURVEY'
);


--
-- TOC entry 914 (class 1247 OID 16512)
-- Name: filetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.filetype AS ENUM (
    'PDF',
    'IMAGE',
    'DOCUMENT',
    'OTHER'
);


--
-- TOC entry 1022 (class 1247 OID 26546)
-- Name: keyconflictstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.keyconflictstatus AS ENUM (
    'NONE',
    'PENDING_REVIEW',
    'RESOLVED'
);


--
-- TOC entry 917 (class 1247 OID 16530)
-- Name: messagetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.messagetype AS ENUM (
    'TEXT',
    'PHOTO',
    'DOCUMENT',
    'VOICE',
    'SYSTEM_NOTIFICATION',
    'video',
    'audio',
    'video_note',
    'VIDEO',
    'AUDIO',
    'VIDEO_NOTE'
);


--
-- TOC entry 920 (class 1247 OID 16554)
-- Name: registrationstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.registrationstatus AS ENUM (
    'PENDING',
    'ACTIVE',
    'REJECTED',
    'UNDER_REVIEW'
);


--
-- TOC entry 923 (class 1247 OID 16564)
-- Name: resolutionaction; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.resolutionaction AS ENUM (
    'reassigned',
    'taken_over',
    'contacted',
    'auto_resolved',
    'TAKEN_OVER',
    'REASSIGNED',
    'CONTACTED',
    'AUTO_RESOLVED'
);


--
-- TOC entry 926 (class 1247 OID 16582)
-- Name: retrystatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.retrystatus AS ENUM (
    'pending',
    'success',
    'failed'
);


--
-- TOC entry 929 (class 1247 OID 16590)
-- Name: sendertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sendertype AS ENUM (
    'USER',
    'STAFF',
    'SYSTEM'
);


--
-- TOC entry 932 (class 1247 OID 16598)
-- Name: settingcategory; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.settingcategory AS ENUM (
    'timeouts',
    'escalation',
    'duty_support',
    'nps',
    'renewal_reminders'
);


--
-- TOC entry 935 (class 1247 OID 16610)
-- Name: settingdatatype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.settingdatatype AS ENUM (
    'integer',
    'json',
    'chat_id',
    'user_id'
);


--
-- TOC entry 938 (class 1247 OID 16620)
-- Name: staffrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.staffrole AS ENUM (
    'MANAGER',
    'TECHNICAL_SUPPORT',
    'DUTY_ENGINEER',
    'ADMINISTRATOR'
);


--
-- TOC entry 941 (class 1247 OID 16630)
-- Name: subscriptionstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.subscriptionstatus AS ENUM (
    'ACTIVE',
    'EXPIRED',
    'NONE'
);


--
-- TOC entry 944 (class 1247 OID 16638)
-- Name: surveytype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.surveytype AS ENUM (
    'loyalty',
    'service_quality',
    'LOYALTY',
    'SERVICE_QUALITY'
);


--
-- TOC entry 947 (class 1247 OID 16648)
-- Name: ticketstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.ticketstatus AS ENUM (
    'NEW',
    'IN_PROGRESS',
    'WAITING_CLIENT',
    'CLOSED',
    'CANCELLED'
);


--
-- TOC entry 950 (class 1247 OID 16660)
-- Name: tickettype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.tickettype AS ENUM (
    'INVOICE',
    'TECHNICAL_SUPPORT',
    'RENEWAL',
    'phone_change',
    'KEY_CONFLICT'
);


--
-- TOC entry 953 (class 1247 OID 16668)
-- Name: uploadertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.uploadertype AS ENUM (
    'USER',
    'STAFF'
);


--
-- TOC entry 956 (class 1247 OID 16674)
-- Name: workmode; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.workmode AS ENUM (
    'REGULAR',
    'EXTENDED',
    'NON_WORKING'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 219 (class 1259 OID 16681)
-- Name: action_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.action_logs (
    id integer NOT NULL,
    action_type public.actiontype NOT NULL,
    ticket_id integer,
    action_details json,
    action_timestamp timestamp without time zone NOT NULL,
    user_id bigint,
    staff_id bigint
);


--
-- TOC entry 220 (class 1259 OID 16689)
-- Name: action_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.action_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5318 (class 0 OID 0)
-- Dependencies: 220
-- Name: action_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.action_logs_id_seq OWNED BY public.action_logs.id;


--
-- TOC entry 221 (class 1259 OID 16690)
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- TOC entry 222 (class 1259 OID 16694)
-- Name: api_retry_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_retry_queue (
    id integer NOT NULL,
    operation character varying(100) NOT NULL,
    payload json NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    status public.retrystatus DEFAULT 'pending'::public.retrystatus NOT NULL,
    next_retry_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    completed_at timestamp without time zone,
    last_error text,
    user_id bigint
);


--
-- TOC entry 223 (class 1259 OID 16709)
-- Name: api_retry_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.api_retry_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5319 (class 0 OID 0)
-- Dependencies: 223
-- Name: api_retry_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.api_retry_queue_id_seq OWNED BY public.api_retry_queue.id;


--
-- TOC entry 224 (class 1259 OID 16710)
-- Name: broadcast_deliveries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.broadcast_deliveries (
    id integer NOT NULL,
    broadcast_id integer NOT NULL,
    delivery_status public.deliverystatus NOT NULL,
    delivered_at timestamp without time zone,
    error_message character varying(512),
    user_id bigint NOT NULL
);


--
-- TOC entry 225 (class 1259 OID 16719)
-- Name: broadcast_deliveries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.broadcast_deliveries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5320 (class 0 OID 0)
-- Dependencies: 225
-- Name: broadcast_deliveries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcast_deliveries_id_seq OWNED BY public.broadcast_deliveries.id;


--
-- TOC entry 226 (class 1259 OID 16720)
-- Name: broadcasts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.broadcasts (
    id integer NOT NULL,
    message_text text NOT NULL,
    broadcast_status public.broadcaststatus NOT NULL,
    target_user_count integer NOT NULL,
    delivered_count integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    sent_at timestamp without time zone,
    created_by_staff_id bigint NOT NULL
);


--
-- TOC entry 227 (class 1259 OID 16732)
-- Name: broadcasts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.broadcasts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5321 (class 0 OID 0)
-- Dependencies: 227
-- Name: broadcasts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcasts_id_seq OWNED BY public.broadcasts.id;


--
-- TOC entry 228 (class 1259 OID 16733)
-- Name: calendar_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.calendar_rules (
    id integer NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    work_mode public.workmode NOT NULL,
    work_start_time time without time zone,
    work_end_time time without time zone,
    rule_priority integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT ck_calendar_rules_date_range CHECK ((end_date >= start_date))
);


--
-- TOC entry 229 (class 1259 OID 16743)
-- Name: calendar_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.calendar_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5322 (class 0 OID 0)
-- Dependencies: 229
-- Name: calendar_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.calendar_rules_id_seq OWNED BY public.calendar_rules.id;


--
-- TOC entry 230 (class 1259 OID 16744)
-- Name: escalations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.escalations (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    escalation_type public.escalationtype NOT NULL,
    is_resolved boolean DEFAULT false NOT NULL,
    resolved_at timestamp without time zone,
    resolved_by_staff_id bigint,
    resolution_action public.resolutionaction,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone
);


--
-- TOC entry 231 (class 1259 OID 16753)
-- Name: escalations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.escalations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5323 (class 0 OID 0)
-- Dependencies: 231
-- Name: escalations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.escalations_id_seq OWNED BY public.escalations.id;


--
-- TOC entry 232 (class 1259 OID 16754)
-- Name: file_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_attachments (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    message_id integer,
    file_type public.filetype NOT NULL,
    telegram_file_id text NOT NULL,
    file_name character varying(256),
    file_size integer,
    uploader_id bigint NOT NULL,
    uploader_type public.uploadertype NOT NULL,
    uploaded_at timestamp without time zone NOT NULL,
    max_file_url text
);


--
-- TOC entry 233 (class 1259 OID 16766)
-- Name: file_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.file_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5324 (class 0 OID 0)
-- Dependencies: 233
-- Name: file_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_attachments_id_seq OWNED BY public.file_attachments.id;


--
-- TOC entry 234 (class 1259 OID 16767)
-- Name: gs_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gs_keys (
    id integer NOT NULL,
    key_number character varying(32) NOT NULL,
    conflict_status public.keyconflictstatus NOT NULL,
    conflict_reported_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    user_id bigint NOT NULL,
    CONSTRAINT ck_gs_keys_key_format CHECK (((key_number)::text ~ '^[0-9]{5}_[0-9]{5}$'::text))
);


--
-- TOC entry 235 (class 1259 OID 16776)
-- Name: gs_keys_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gs_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5325 (class 0 OID 0)
-- Dependencies: 235
-- Name: gs_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gs_keys_id_seq OWNED BY public.gs_keys.id;


--
-- TOC entry 236 (class 1259 OID 16777)
-- Name: manager_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manager_assignments (
    id integer NOT NULL,
    organization_inn character varying(12) NOT NULL,
    assigned_at timestamp without time zone NOT NULL,
    user_id bigint NOT NULL,
    manager_id bigint NOT NULL
);


--
-- TOC entry 237 (class 1259 OID 16785)
-- Name: manager_assignments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manager_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5326 (class 0 OID 0)
-- Dependencies: 237
-- Name: manager_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manager_assignments_id_seq OWNED BY public.manager_assignments.id;


--
-- TOC entry 238 (class 1259 OID 16786)
-- Name: max_messenger_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.max_messenger_data (
    id integer NOT NULL,
    user_id bigint NOT NULL,
    max_user_id bigint NOT NULL,
    max_chat_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- TOC entry 239 (class 1259 OID 16795)
-- Name: max_messenger_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.max_messenger_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5327 (class 0 OID 0)
-- Dependencies: 239
-- Name: max_messenger_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.max_messenger_data_id_seq OWNED BY public.max_messenger_data.id;


--
-- TOC entry 240 (class 1259 OID 16796)
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    sender_type public.sendertype NOT NULL,
    sender_id bigint,
    message_text character varying NOT NULL,
    message_type public.messagetype NOT NULL,
    sent_at timestamp without time zone NOT NULL
);


--
-- TOC entry 241 (class 1259 OID 16807)
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5328 (class 0 OID 0)
-- Dependencies: 241
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- TOC entry 242 (class 1259 OID 16808)
-- Name: notification_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_events (
    id integer NOT NULL,
    event_type public.eventtype NOT NULL,
    event_status public.eventstatus NOT NULL,
    scheduled_for timestamp without time zone NOT NULL,
    sent_at timestamp without time zone,
    related_ticket_id integer,
    event_data json,
    created_at timestamp without time zone NOT NULL,
    user_id bigint NOT NULL
);


--
-- TOC entry 243 (class 1259 OID 16819)
-- Name: notification_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notification_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5329 (class 0 OID 0)
-- Dependencies: 243
-- Name: notification_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notification_events_id_seq OWNED BY public.notification_events.id;


--
-- TOC entry 244 (class 1259 OID 16820)
-- Name: nps_responses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nps_responses (
    id integer NOT NULL,
    user_id bigint NOT NULL,
    survey_type public.surveytype NOT NULL,
    rating integer NOT NULL,
    trigger_event_id integer NOT NULL,
    sent_at timestamp without time zone NOT NULL,
    responded_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone,
    feedback_comment text
);


--
-- TOC entry 245 (class 1259 OID 16833)
-- Name: nps_responses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nps_responses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5330 (class 0 OID 0)
-- Dependencies: 245
-- Name: nps_responses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nps_responses_id_seq OWNED BY public.nps_responses.id;


--
-- TOC entry 246 (class 1259 OID 16834)
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    inn character varying(12) NOT NULL,
    organization_name character varying(256),
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT ck_organizations_inn_format CHECK ((((inn)::text ~ '^[0-9]{10}$'::text) OR ((inn)::text ~ '^[0-9]{12}$'::text)))
);


--
-- TOC entry 247 (class 1259 OID 16840)
-- Name: staff_members_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_members_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 248 (class 1259 OID 16841)
-- Name: staff_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_members (
    tg_user_id bigint,
    full_name character varying(128) NOT NULL,
    "position" character varying(128) NOT NULL,
    staff_role public.staffrole NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone,
    max_user_id bigint,
    id bigint DEFAULT nextval('public.staff_members_id_seq'::regclass) NOT NULL,
    backup_manager_1_id bigint,
    backup_manager_2_id bigint,
    max_chat_id bigint
);


--
-- TOC entry 249 (class 1259 OID 16851)
-- Name: staff_members_tg_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_members_tg_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5331 (class 0 OID 0)
-- Dependencies: 249
-- Name: staff_members_tg_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.staff_members_tg_user_id_seq OWNED BY public.staff_members.tg_user_id;


--
-- TOC entry 250 (class 1259 OID 16852)
-- Name: system_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_settings (
    id integer NOT NULL,
    key character varying(100) NOT NULL,
    category public.settingcategory NOT NULL,
    value text,
    data_type public.settingdatatype NOT NULL,
    default_value text NOT NULL,
    min_value integer,
    max_value integer,
    description text NOT NULL,
    display_name character varying(200) NOT NULL,
    requires_test boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by bigint
);


--
-- TOC entry 251 (class 1259 OID 16868)
-- Name: system_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.system_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5332 (class 0 OID 0)
-- Dependencies: 251
-- Name: system_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_settings_id_seq OWNED BY public.system_settings.id;


--
-- TOC entry 252 (class 1259 OID 16869)
-- Name: ticket_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticket_keys (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    key_id integer NOT NULL,
    added_at timestamp without time zone NOT NULL
);


--
-- TOC entry 253 (class 1259 OID 16876)
-- Name: ticket_keys_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ticket_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5333 (class 0 OID 0)
-- Dependencies: 253
-- Name: ticket_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ticket_keys_id_seq OWNED BY public.ticket_keys.id;


--
-- TOC entry 254 (class 1259 OID 16877)
-- Name: tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tickets (
    id integer NOT NULL,
    ticket_type public.tickettype NOT NULL,
    ticket_status public.ticketstatus NOT NULL,
    organization_inn character varying(12),
    description character varying,
    delivery_method public.deliverymethod NOT NULL,
    delivery_email character varying(256),
    escalation_level integer NOT NULL,
    escalated_at timestamp without time zone,
    closed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone,
    user_id bigint NOT NULL,
    assigned_staff_id bigint,
    escalation_task_reminder_id character varying(255),
    escalation_task_escalation_id character varying(255),
    is_escalated boolean DEFAULT false NOT NULL,
    old_phone character varying(20),
    new_phone character varying(20),
    resolution_comment character varying,
    queue_notification_sent_at timestamp without time zone,
    CONSTRAINT ck_tickets_escalation_level CHECK ((escalation_level = ANY (ARRAY[0, 1, 2])))
);


--
-- TOC entry 5334 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.escalation_task_reminder_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.escalation_task_reminder_id IS 'ID Celery задачи напоминания';


--
-- TOC entry 5335 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.escalation_task_escalation_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.escalation_task_escalation_id IS 'ID Celery задачи эскалации';


--
-- TOC entry 5336 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.is_escalated; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.is_escalated IS 'Флаг эскалированной заявки';


--
-- TOC entry 5337 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.old_phone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.old_phone IS 'Old phone number for phone change requests';


--
-- TOC entry 5338 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.new_phone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.new_phone IS 'New phone number for phone change requests';


--
-- TOC entry 5339 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.resolution_comment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.resolution_comment IS 'Resolution comment for closed tickets';


--
-- TOC entry 5340 (class 0 OID 0)
-- Dependencies: 254
-- Name: COLUMN tickets.queue_notification_sent_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.queue_notification_sent_at IS 'Timestamp when queue notification was sent (prevents duplicate notifications)';


--
-- TOC entry 255 (class 1259 OID 16892)
-- Name: tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tickets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5341 (class 0 OID 0)
-- Dependencies: 255
-- Name: tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tickets_id_seq OWNED BY public.tickets.id;


--
-- TOC entry 256 (class 1259 OID 16893)
-- Name: user_organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_organizations (
    id integer NOT NULL,
    organization_inn character varying(12) NOT NULL,
    added_at timestamp without time zone NOT NULL,
    user_id bigint NOT NULL
);


--
-- TOC entry 257 (class 1259 OID 16900)
-- Name: user_organizations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_organizations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5342 (class 0 OID 0)
-- Dependencies: 257
-- Name: user_organizations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_organizations_id_seq OWNED BY public.user_organizations.id;


--
-- TOC entry 258 (class 1259 OID 16901)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 259 (class 1259 OID 16902)
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    tg_user_id bigint,
    phone_number character varying(15) NOT NULL,
    username character varying(32),
    first_name character varying(64),
    last_name character varying(64),
    full_name character varying(128),
    registration_status public.registrationstatus NOT NULL,
    subscription_status public.subscriptionstatus NOT NULL,
    subscription_end_date timestamp without time zone,
    notification_preferences boolean NOT NULL,
    last_nps_sent_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone,
    max_user_id bigint,
    id bigint DEFAULT nextval('public.users_id_seq'::regclass) NOT NULL,
    default_manager_id bigint,
    email character varying(255),
    middle_name character varying(64),
    CONSTRAINT ck_users_phone_format CHECK (((phone_number)::text ~ '^\+?[0-9]{10,15}$'::text))
);


--
-- TOC entry 260 (class 1259 OID 16915)
-- Name: users_tg_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_tg_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 5343 (class 0 OID 0)
-- Dependencies: 260
-- Name: users_tg_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_tg_user_id_seq OWNED BY public.users.tg_user_id;


--
-- TOC entry 5025 (class 2604 OID 16916)
-- Name: action_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs ALTER COLUMN id SET DEFAULT nextval('public.action_logs_id_seq'::regclass);


--
-- TOC entry 5026 (class 2604 OID 16917)
-- Name: api_retry_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue ALTER COLUMN id SET DEFAULT nextval('public.api_retry_queue_id_seq'::regclass);


--
-- TOC entry 5030 (class 2604 OID 16918)
-- Name: broadcast_deliveries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries ALTER COLUMN id SET DEFAULT nextval('public.broadcast_deliveries_id_seq'::regclass);


--
-- TOC entry 5031 (class 2604 OID 16919)
-- Name: broadcasts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts ALTER COLUMN id SET DEFAULT nextval('public.broadcasts_id_seq'::regclass);


--
-- TOC entry 5032 (class 2604 OID 16920)
-- Name: calendar_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calendar_rules ALTER COLUMN id SET DEFAULT nextval('public.calendar_rules_id_seq'::regclass);


--
-- TOC entry 5033 (class 2604 OID 16921)
-- Name: escalations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations ALTER COLUMN id SET DEFAULT nextval('public.escalations_id_seq'::regclass);


--
-- TOC entry 5035 (class 2604 OID 16922)
-- Name: file_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments ALTER COLUMN id SET DEFAULT nextval('public.file_attachments_id_seq'::regclass);


--
-- TOC entry 5036 (class 2604 OID 16923)
-- Name: gs_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys ALTER COLUMN id SET DEFAULT nextval('public.gs_keys_id_seq'::regclass);


--
-- TOC entry 5037 (class 2604 OID 16924)
-- Name: manager_assignments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments ALTER COLUMN id SET DEFAULT nextval('public.manager_assignments_id_seq'::regclass);


--
-- TOC entry 5038 (class 2604 OID 16925)
-- Name: max_messenger_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data ALTER COLUMN id SET DEFAULT nextval('public.max_messenger_data_id_seq'::regclass);


--
-- TOC entry 5040 (class 2604 OID 16926)
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- TOC entry 5041 (class 2604 OID 16927)
-- Name: notification_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events ALTER COLUMN id SET DEFAULT nextval('public.notification_events_id_seq'::regclass);


--
-- TOC entry 5042 (class 2604 OID 16928)
-- Name: nps_responses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses ALTER COLUMN id SET DEFAULT nextval('public.nps_responses_id_seq'::regclass);


--
-- TOC entry 5043 (class 2604 OID 16929)
-- Name: staff_members tg_user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members ALTER COLUMN tg_user_id SET DEFAULT nextval('public.staff_members_tg_user_id_seq'::regclass);


--
-- TOC entry 5045 (class 2604 OID 16930)
-- Name: system_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings ALTER COLUMN id SET DEFAULT nextval('public.system_settings_id_seq'::regclass);


--
-- TOC entry 5047 (class 2604 OID 16931)
-- Name: ticket_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys ALTER COLUMN id SET DEFAULT nextval('public.ticket_keys_id_seq'::regclass);


--
-- TOC entry 5048 (class 2604 OID 16932)
-- Name: tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets ALTER COLUMN id SET DEFAULT nextval('public.tickets_id_seq'::regclass);


--
-- TOC entry 5050 (class 2604 OID 16933)
-- Name: user_organizations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations ALTER COLUMN id SET DEFAULT nextval('public.user_organizations_id_seq'::regclass);


--
-- TOC entry 5051 (class 2604 OID 16934)
-- Name: users tg_user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN tg_user_id SET DEFAULT nextval('public.users_tg_user_id_seq'::regclass);


--
-- TOC entry 5059 (class 2606 OID 16936)
-- Name: action_logs action_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_pkey PRIMARY KEY (id);


--
-- TOC entry 5061 (class 2606 OID 16938)
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- TOC entry 5063 (class 2606 OID 16940)
-- Name: api_retry_queue api_retry_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue
    ADD CONSTRAINT api_retry_queue_pkey PRIMARY KEY (id);


--
-- TOC entry 5065 (class 2606 OID 16942)
-- Name: broadcast_deliveries broadcast_deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_pkey PRIMARY KEY (id);


--
-- TOC entry 5069 (class 2606 OID 16944)
-- Name: broadcasts broadcasts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_pkey PRIMARY KEY (id);


--
-- TOC entry 5071 (class 2606 OID 16946)
-- Name: calendar_rules calendar_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calendar_rules
    ADD CONSTRAINT calendar_rules_pkey PRIMARY KEY (id);


--
-- TOC entry 5073 (class 2606 OID 16948)
-- Name: escalations escalations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_pkey PRIMARY KEY (id);


--
-- TOC entry 5077 (class 2606 OID 16950)
-- Name: file_attachments file_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_pkey PRIMARY KEY (id);


--
-- TOC entry 5079 (class 2606 OID 16952)
-- Name: gs_keys gs_keys_key_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_key_number_key UNIQUE (key_number);


--
-- TOC entry 5081 (class 2606 OID 16954)
-- Name: gs_keys gs_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_pkey PRIMARY KEY (id);


--
-- TOC entry 5083 (class 2606 OID 16956)
-- Name: manager_assignments manager_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_pkey PRIMARY KEY (id);


--
-- TOC entry 5090 (class 2606 OID 16958)
-- Name: max_messenger_data max_messenger_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT max_messenger_data_pkey PRIMARY KEY (id);


--
-- TOC entry 5096 (class 2606 OID 16960)
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- TOC entry 5098 (class 2606 OID 16962)
-- Name: notification_events notification_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_pkey PRIMARY KEY (id);


--
-- TOC entry 5106 (class 2606 OID 16964)
-- Name: nps_responses nps_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses
    ADD CONSTRAINT nps_responses_pkey PRIMARY KEY (id);


--
-- TOC entry 5108 (class 2606 OID 16966)
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (inn);


--
-- TOC entry 5113 (class 2606 OID 16968)
-- Name: staff_members staff_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_pkey PRIMARY KEY (id);


--
-- TOC entry 5117 (class 2606 OID 16970)
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (id);


--
-- TOC entry 5119 (class 2606 OID 16972)
-- Name: ticket_keys ticket_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_pkey PRIMARY KEY (id);


--
-- TOC entry 5124 (class 2606 OID 16974)
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);


--
-- TOC entry 5067 (class 2606 OID 16976)
-- Name: broadcast_deliveries uq_broadcast_user_delivery; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT uq_broadcast_user_delivery UNIQUE (broadcast_id, user_id);


--
-- TOC entry 5092 (class 2606 OID 16978)
-- Name: max_messenger_data uq_max_messenger_max_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT uq_max_messenger_max_user_id UNIQUE (max_user_id);


--
-- TOC entry 5094 (class 2606 OID 16980)
-- Name: max_messenger_data uq_max_messenger_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT uq_max_messenger_user_id UNIQUE (user_id);


--
-- TOC entry 5121 (class 2606 OID 16982)
-- Name: ticket_keys uq_ticket_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT uq_ticket_key UNIQUE (ticket_id, key_id);


--
-- TOC entry 5085 (class 2606 OID 16984)
-- Name: manager_assignments uq_user_org_assignment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT uq_user_org_assignment UNIQUE (user_id, organization_inn);


--
-- TOC entry 5126 (class 2606 OID 16986)
-- Name: user_organizations uq_user_organization; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT uq_user_organization UNIQUE (user_id, organization_inn);


--
-- TOC entry 5128 (class 2606 OID 16988)
-- Name: user_organizations user_organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_pkey PRIMARY KEY (id);


--
-- TOC entry 5132 (class 2606 OID 16990)
-- Name: users users_phone_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_phone_number_key UNIQUE (phone_number);


--
-- TOC entry 5134 (class 2606 OID 16992)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 5099 (class 1259 OID 16993)
-- Name: idx_nps_type_responded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nps_type_responded ON public.nps_responses USING btree (survey_type, responded_at);


--
-- TOC entry 5100 (class 1259 OID 16994)
-- Name: idx_nps_user_responded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nps_user_responded ON public.nps_responses USING btree (user_id, responded_at);


--
-- TOC entry 5074 (class 1259 OID 16995)
-- Name: ix_escalations_is_resolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_escalations_is_resolved ON public.escalations USING btree (is_resolved);


--
-- TOC entry 5075 (class 1259 OID 16996)
-- Name: ix_escalations_ticket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_escalations_ticket_id ON public.escalations USING btree (ticket_id);


--
-- TOC entry 5086 (class 1259 OID 16997)
-- Name: ix_max_messenger_data_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_max_chat_id ON public.max_messenger_data USING btree (max_chat_id);


--
-- TOC entry 5087 (class 1259 OID 16998)
-- Name: ix_max_messenger_data_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_max_user_id ON public.max_messenger_data USING btree (max_user_id);


--
-- TOC entry 5088 (class 1259 OID 16999)
-- Name: ix_max_messenger_data_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_user_id ON public.max_messenger_data USING btree (user_id);


--
-- TOC entry 5101 (class 1259 OID 17000)
-- Name: ix_nps_responses_responded_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_responded_at ON public.nps_responses USING btree (responded_at);


--
-- TOC entry 5102 (class 1259 OID 17001)
-- Name: ix_nps_responses_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_sent_at ON public.nps_responses USING btree (sent_at);


--
-- TOC entry 5103 (class 1259 OID 17002)
-- Name: ix_nps_responses_survey_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_survey_type ON public.nps_responses USING btree (survey_type);


--
-- TOC entry 5104 (class 1259 OID 17003)
-- Name: ix_nps_responses_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_user_id ON public.nps_responses USING btree (user_id);


--
-- TOC entry 5109 (class 1259 OID 17004)
-- Name: ix_staff_members_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_members_max_chat_id ON public.staff_members USING btree (max_chat_id);


--
-- TOC entry 5110 (class 1259 OID 17005)
-- Name: ix_staff_members_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_members_max_user_id ON public.staff_members USING btree (max_user_id) WHERE (max_user_id IS NOT NULL);


--
-- TOC entry 5111 (class 1259 OID 17006)
-- Name: ix_staff_members_tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_members_tg_user_id ON public.staff_members USING btree (tg_user_id);


--
-- TOC entry 5114 (class 1259 OID 17007)
-- Name: ix_system_settings_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_settings_category ON public.system_settings USING btree (category);


--
-- TOC entry 5115 (class 1259 OID 17008)
-- Name: ix_system_settings_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_system_settings_key ON public.system_settings USING btree (key);


--
-- TOC entry 5122 (class 1259 OID 17009)
-- Name: ix_tickets_is_escalated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_is_escalated ON public.tickets USING btree (is_escalated);


--
-- TOC entry 5129 (class 1259 OID 17010)
-- Name: ix_users_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_max_user_id ON public.users USING btree (max_user_id) WHERE (max_user_id IS NOT NULL);


--
-- TOC entry 5130 (class 1259 OID 17011)
-- Name: ix_users_tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_tg_user_id ON public.users USING btree (tg_user_id);


--
-- TOC entry 5135 (class 2606 OID 17012)
-- Name: action_logs action_logs_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_staff_id_fkey FOREIGN KEY (staff_id) REFERENCES public.staff_members(id);


--
-- TOC entry 5136 (class 2606 OID 17017)
-- Name: action_logs action_logs_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);


--
-- TOC entry 5137 (class 2606 OID 17022)
-- Name: action_logs action_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5138 (class 2606 OID 17027)
-- Name: api_retry_queue api_retry_queue_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue
    ADD CONSTRAINT api_retry_queue_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5139 (class 2606 OID 17032)
-- Name: broadcast_deliveries broadcast_deliveries_broadcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_broadcast_id_fkey FOREIGN KEY (broadcast_id) REFERENCES public.broadcasts(id);


--
-- TOC entry 5140 (class 2606 OID 17037)
-- Name: broadcast_deliveries broadcast_deliveries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5141 (class 2606 OID 17042)
-- Name: broadcasts broadcasts_created_by_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_created_by_staff_id_fkey FOREIGN KEY (created_by_staff_id) REFERENCES public.staff_members(id);


--
-- TOC entry 5142 (class 2606 OID 17047)
-- Name: escalations escalations_resolved_by_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_resolved_by_staff_id_fkey FOREIGN KEY (resolved_by_staff_id) REFERENCES public.staff_members(id) ON DELETE SET NULL;


--
-- TOC entry 5143 (class 2606 OID 17052)
-- Name: escalations escalations_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5144 (class 2606 OID 17057)
-- Name: file_attachments file_attachments_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id);


--
-- TOC entry 5145 (class 2606 OID 17062)
-- Name: file_attachments file_attachments_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5146 (class 2606 OID 17067)
-- Name: gs_keys gs_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5147 (class 2606 OID 17072)
-- Name: manager_assignments manager_assignments_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.staff_members(id);


--
-- TOC entry 5148 (class 2606 OID 17077)
-- Name: manager_assignments manager_assignments_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- TOC entry 5149 (class 2606 OID 17082)
-- Name: manager_assignments manager_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5150 (class 2606 OID 17087)
-- Name: max_messenger_data max_messenger_data_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT max_messenger_data_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 5151 (class 2606 OID 17092)
-- Name: messages messages_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5152 (class 2606 OID 17097)
-- Name: notification_events notification_events_related_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_related_ticket_id_fkey FOREIGN KEY (related_ticket_id) REFERENCES public.tickets(id);


--
-- TOC entry 5153 (class 2606 OID 17102)
-- Name: notification_events notification_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5154 (class 2606 OID 17107)
-- Name: nps_responses nps_responses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses
    ADD CONSTRAINT nps_responses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 5155 (class 2606 OID 17112)
-- Name: staff_members staff_members_backup_manager_1_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_backup_manager_1_id_fkey FOREIGN KEY (backup_manager_1_id) REFERENCES public.staff_members(id);


--
-- TOC entry 5156 (class 2606 OID 17117)
-- Name: staff_members staff_members_backup_manager_2_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_backup_manager_2_id_fkey FOREIGN KEY (backup_manager_2_id) REFERENCES public.staff_members(id);


--
-- TOC entry 5157 (class 2606 OID 17122)
-- Name: system_settings system_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.staff_members(id);


--
-- TOC entry 5158 (class 2606 OID 17127)
-- Name: ticket_keys ticket_keys_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_key_id_fkey FOREIGN KEY (key_id) REFERENCES public.gs_keys(id);


--
-- TOC entry 5159 (class 2606 OID 17132)
-- Name: ticket_keys ticket_keys_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5160 (class 2606 OID 17137)
-- Name: tickets tickets_assigned_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_assigned_staff_id_fkey FOREIGN KEY (assigned_staff_id) REFERENCES public.staff_members(id) ON DELETE SET NULL;


--
-- TOC entry 5161 (class 2606 OID 17142)
-- Name: tickets tickets_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- TOC entry 5162 (class 2606 OID 17147)
-- Name: tickets tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5163 (class 2606 OID 17152)
-- Name: user_organizations user_organizations_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- TOC entry 5164 (class 2606 OID 17157)
-- Name: user_organizations user_organizations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 5165 (class 2606 OID 17162)
-- Name: users users_default_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_default_manager_id_fkey FOREIGN KEY (default_manager_id) REFERENCES public.staff_members(id);


-- Completed on 2026-03-21 16:13:09

--
-- PostgreSQL database dump complete
--

\unrestrict XaywYSYjFPbtejbuvHavRbNlkYpp79og4AkSepNNvpuRQDUhK5XoQnoWHDfhojy

