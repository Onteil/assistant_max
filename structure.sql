--
-- PostgreSQL database dump
--

-- Dumped from database version 12.0
-- Dumped by pg_dump version 14.4

-- Started on 2026-03-10 14:17:44

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 760 (class 1247 OID 97469)
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
    'API_RETRY_FAILED'
);


--
-- TOC entry 746 (class 1247 OID 97412)
-- Name: broadcaststatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.broadcaststatus AS ENUM (
    'DRAFT',
    'SENDING',
    'COMPLETED',
    'FAILED'
);


--
-- TOC entry 704 (class 1247 OID 96998)
-- Name: deliverymethod; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.deliverymethod AS ENUM (
    'TELEGRAM',
    'EMAIL',
    'NONE'
);


--
-- TOC entry 753 (class 1247 OID 97438)
-- Name: deliverystatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.deliverystatus AS ENUM (
    'PENDING',
    'DELIVERED',
    'FAILED'
);


--
-- TOC entry 792 (class 1247 OID 98216)
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
-- TOC entry 770 (class 1247 OID 97522)
-- Name: eventstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventstatus AS ENUM (
    'SCHEDULED',
    'SENT',
    'FAILED',
    'CANCELLED'
);


--
-- TOC entry 767 (class 1247 OID 97514)
-- Name: eventtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventtype AS ENUM (
    'RENEWAL_REMINDER_30',
    'RENEWAL_REMINDER_7',
    'NPS_SURVEY'
);


--
-- TOC entry 728 (class 1247 OID 97108)
-- Name: filetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.filetype AS ENUM (
    'PDF',
    'IMAGE',
    'DOCUMENT',
    'OTHER'
);


--
-- TOC entry 687 (class 1247 OID 96931)
-- Name: keyconflictstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.keyconflictstatus AS ENUM (
    'NONE',
    'PENDING_REVIEW',
    'RESOLVED'
);


--
-- TOC entry 718 (class 1247 OID 97060)
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
-- TOC entry 677 (class 1247 OID 96900)
-- Name: registrationstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.registrationstatus AS ENUM (
    'PENDING',
    'ACTIVE',
    'REJECTED',
    'UNDER_REVIEW'
);


--
-- TOC entry 795 (class 1247 OID 98222)
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
-- TOC entry 777 (class 1247 OID 97693)
-- Name: retrystatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.retrystatus AS ENUM (
    'pending',
    'success',
    'failed'
);


--
-- TOC entry 715 (class 1247 OID 97052)
-- Name: sendertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sendertype AS ENUM (
    'USER',
    'STAFF',
    'SYSTEM'
);


--
-- TOC entry 805 (class 1247 OID 98376)
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
-- TOC entry 802 (class 1247 OID 98367)
-- Name: settingdatatype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.settingdatatype AS ENUM (
    'integer',
    'json',
    'chat_id',
    'user_id'
);


--
-- TOC entry 670 (class 1247 OID 96872)
-- Name: staffrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.staffrole AS ENUM (
    'MANAGER',
    'TECHNICAL_SUPPORT',
    'DUTY_ENGINEER',
    'ADMINISTRATOR'
);


--
-- TOC entry 680 (class 1247 OID 96908)
-- Name: subscriptionstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.subscriptionstatus AS ENUM (
    'ACTIVE',
    'EXPIRED',
    'NONE'
);


--
-- TOC entry 813 (class 1247 OID 98407)
-- Name: surveytype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.surveytype AS ENUM (
    'loyalty',
    'service_quality',
    'LOYALTY',
    'SERVICE_QUALITY'
);


--
-- TOC entry 701 (class 1247 OID 96986)
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
-- TOC entry 698 (class 1247 OID 96978)
-- Name: tickettype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.tickettype AS ENUM (
    'INVOICE',
    'TECHNICAL_SUPPORT',
    'RENEWAL'
);


--
-- TOC entry 731 (class 1247 OID 97118)
-- Name: uploadertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.uploadertype AS ENUM (
    'USER',
    'STAFF'
);


--
-- TOC entry 739 (class 1247 OID 97397)
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
-- TOC entry 229 (class 1259 OID 97489)
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
-- TOC entry 228 (class 1259 OID 97487)
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
-- TOC entry 3207 (class 0 OID 0)
-- Dependencies: 228
-- Name: action_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.action_logs_id_seq OWNED BY public.action_logs.id;


--
-- TOC entry 202 (class 1259 OID 96861)
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- TOC entry 233 (class 1259 OID 97701)
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
-- TOC entry 232 (class 1259 OID 97699)
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
-- TOC entry 3208 (class 0 OID 0)
-- Dependencies: 232
-- Name: api_retry_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.api_retry_queue_id_seq OWNED BY public.api_retry_queue.id;


--
-- TOC entry 227 (class 1259 OID 97447)
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
-- TOC entry 226 (class 1259 OID 97445)
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
-- TOC entry 3209 (class 0 OID 0)
-- Dependencies: 226
-- Name: broadcast_deliveries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcast_deliveries_id_seq OWNED BY public.broadcast_deliveries.id;


--
-- TOC entry 225 (class 1259 OID 97423)
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
-- TOC entry 224 (class 1259 OID 97421)
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
-- TOC entry 3210 (class 0 OID 0)
-- Dependencies: 224
-- Name: broadcasts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcasts_id_seq OWNED BY public.broadcasts.id;


--
-- TOC entry 223 (class 1259 OID 97405)
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
-- TOC entry 222 (class 1259 OID 97403)
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
-- TOC entry 3211 (class 0 OID 0)
-- Dependencies: 222
-- Name: calendar_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.calendar_rules_id_seq OWNED BY public.calendar_rules.id;


--
-- TOC entry 237 (class 1259 OID 98233)
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
-- TOC entry 236 (class 1259 OID 98231)
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
-- TOC entry 3212 (class 0 OID 0)
-- Dependencies: 236
-- Name: escalations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.escalations_id_seq OWNED BY public.escalations.id;


--
-- TOC entry 221 (class 1259 OID 97125)
-- Name: file_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_attachments (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    message_id integer,
    file_type public.filetype NOT NULL,
    telegram_file_id character varying(256) NOT NULL,
    file_name character varying(256),
    file_size integer,
    uploader_id bigint NOT NULL,
    uploader_type public.uploadertype NOT NULL,
    uploaded_at timestamp without time zone NOT NULL
);


--
-- TOC entry 220 (class 1259 OID 97123)
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
-- TOC entry 3213 (class 0 OID 0)
-- Dependencies: 220
-- Name: file_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_attachments_id_seq OWNED BY public.file_attachments.id;


--
-- TOC entry 209 (class 1259 OID 96939)
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
-- TOC entry 208 (class 1259 OID 96937)
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
-- TOC entry 3214 (class 0 OID 0)
-- Dependencies: 208
-- Name: gs_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gs_keys_id_seq OWNED BY public.gs_keys.id;


--
-- TOC entry 211 (class 1259 OID 96954)
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
-- TOC entry 210 (class 1259 OID 96952)
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
-- TOC entry 3215 (class 0 OID 0)
-- Dependencies: 210
-- Name: manager_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manager_assignments_id_seq OWNED BY public.manager_assignments.id;


--
-- TOC entry 243 (class 1259 OID 106478)
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
-- TOC entry 242 (class 1259 OID 106476)
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
-- TOC entry 3216 (class 0 OID 0)
-- Dependencies: 242
-- Name: max_messenger_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.max_messenger_data_id_seq OWNED BY public.max_messenger_data.id;


--
-- TOC entry 217 (class 1259 OID 97073)
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
-- TOC entry 216 (class 1259 OID 97071)
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
-- TOC entry 3217 (class 0 OID 0)
-- Dependencies: 216
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- TOC entry 231 (class 1259 OID 97533)
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
-- TOC entry 230 (class 1259 OID 97531)
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
-- TOC entry 3218 (class 0 OID 0)
-- Dependencies: 230
-- Name: notification_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notification_events_id_seq OWNED BY public.notification_events.id;


--
-- TOC entry 241 (class 1259 OID 98413)
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
-- TOC entry 240 (class 1259 OID 98411)
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
-- TOC entry 3219 (class 0 OID 0)
-- Dependencies: 240
-- Name: nps_responses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nps_responses_id_seq OWNED BY public.nps_responses.id;


--
-- TOC entry 203 (class 1259 OID 96866)
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    inn character varying(12) NOT NULL,
    organization_name character varying(256),
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT ck_organizations_inn_format CHECK ((((inn)::text ~ '^[0-9]{10}$'::text) OR ((inn)::text ~ '^[0-9]{12}$'::text)))
);


--
-- TOC entry 235 (class 1259 OID 97776)
-- Name: staff_members_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_members_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 205 (class 1259 OID 96883)
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
-- TOC entry 204 (class 1259 OID 96881)
-- Name: staff_members_tg_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_members_tg_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 3220 (class 0 OID 0)
-- Dependencies: 204
-- Name: staff_members_tg_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.staff_members_tg_user_id_seq OWNED BY public.staff_members.tg_user_id;


--
-- TOC entry 239 (class 1259 OID 98389)
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
-- TOC entry 238 (class 1259 OID 98387)
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
-- TOC entry 3221 (class 0 OID 0)
-- Dependencies: 238
-- Name: system_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_settings_id_seq OWNED BY public.system_settings.id;


--
-- TOC entry 219 (class 1259 OID 97089)
-- Name: ticket_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticket_keys (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    key_id integer NOT NULL,
    added_at timestamp without time zone NOT NULL
);


--
-- TOC entry 218 (class 1259 OID 97087)
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
-- TOC entry 3222 (class 0 OID 0)
-- Dependencies: 218
-- Name: ticket_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ticket_keys_id_seq OWNED BY public.ticket_keys.id;


--
-- TOC entry 213 (class 1259 OID 97007)
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
    CONSTRAINT ck_tickets_escalation_level CHECK ((escalation_level = ANY (ARRAY[0, 1, 2])))
);


--
-- TOC entry 3223 (class 0 OID 0)
-- Dependencies: 213
-- Name: COLUMN tickets.escalation_task_reminder_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.escalation_task_reminder_id IS 'ID Celery задачи напоминания';


--
-- TOC entry 3224 (class 0 OID 0)
-- Dependencies: 213
-- Name: COLUMN tickets.escalation_task_escalation_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.escalation_task_escalation_id IS 'ID Celery задачи эскалации';


--
-- TOC entry 3225 (class 0 OID 0)
-- Dependencies: 213
-- Name: COLUMN tickets.is_escalated; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.is_escalated IS 'Флаг эскалированной заявки';


--
-- TOC entry 212 (class 1259 OID 97005)
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
-- TOC entry 3226 (class 0 OID 0)
-- Dependencies: 212
-- Name: tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tickets_id_seq OWNED BY public.tickets.id;


--
-- TOC entry 215 (class 1259 OID 97033)
-- Name: user_organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_organizations (
    id integer NOT NULL,
    organization_inn character varying(12) NOT NULL,
    added_at timestamp without time zone NOT NULL,
    user_id bigint NOT NULL
);


--
-- TOC entry 214 (class 1259 OID 97031)
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
-- TOC entry 3227 (class 0 OID 0)
-- Dependencies: 214
-- Name: user_organizations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_organizations_id_seq OWNED BY public.user_organizations.id;


--
-- TOC entry 234 (class 1259 OID 97722)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 207 (class 1259 OID 96917)
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
-- TOC entry 206 (class 1259 OID 96915)
-- Name: users_tg_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_tg_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 3228 (class 0 OID 0)
-- Dependencies: 206
-- Name: users_tg_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_tg_user_id_seq OWNED BY public.users.tg_user_id;


--
-- TOC entry 2955 (class 2604 OID 97492)
-- Name: action_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs ALTER COLUMN id SET DEFAULT nextval('public.action_logs_id_seq'::regclass);


--
-- TOC entry 2957 (class 2604 OID 97704)
-- Name: api_retry_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue ALTER COLUMN id SET DEFAULT nextval('public.api_retry_queue_id_seq'::regclass);


--
-- TOC entry 2954 (class 2604 OID 97450)
-- Name: broadcast_deliveries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries ALTER COLUMN id SET DEFAULT nextval('public.broadcast_deliveries_id_seq'::regclass);


--
-- TOC entry 2953 (class 2604 OID 97426)
-- Name: broadcasts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts ALTER COLUMN id SET DEFAULT nextval('public.broadcasts_id_seq'::regclass);


--
-- TOC entry 2951 (class 2604 OID 97408)
-- Name: calendar_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calendar_rules ALTER COLUMN id SET DEFAULT nextval('public.calendar_rules_id_seq'::regclass);


--
-- TOC entry 2961 (class 2604 OID 98236)
-- Name: escalations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations ALTER COLUMN id SET DEFAULT nextval('public.escalations_id_seq'::regclass);


--
-- TOC entry 2950 (class 2604 OID 97128)
-- Name: file_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments ALTER COLUMN id SET DEFAULT nextval('public.file_attachments_id_seq'::regclass);


--
-- TOC entry 2941 (class 2604 OID 96942)
-- Name: gs_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys ALTER COLUMN id SET DEFAULT nextval('public.gs_keys_id_seq'::regclass);


--
-- TOC entry 2943 (class 2604 OID 96957)
-- Name: manager_assignments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments ALTER COLUMN id SET DEFAULT nextval('public.manager_assignments_id_seq'::regclass);


--
-- TOC entry 2966 (class 2604 OID 106481)
-- Name: max_messenger_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data ALTER COLUMN id SET DEFAULT nextval('public.max_messenger_data_id_seq'::regclass);


--
-- TOC entry 2948 (class 2604 OID 97076)
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- TOC entry 2956 (class 2604 OID 97536)
-- Name: notification_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events ALTER COLUMN id SET DEFAULT nextval('public.notification_events_id_seq'::regclass);


--
-- TOC entry 2965 (class 2604 OID 98416)
-- Name: nps_responses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses ALTER COLUMN id SET DEFAULT nextval('public.nps_responses_id_seq'::regclass);


--
-- TOC entry 2936 (class 2604 OID 96886)
-- Name: staff_members tg_user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members ALTER COLUMN tg_user_id SET DEFAULT nextval('public.staff_members_tg_user_id_seq'::regclass);


--
-- TOC entry 2963 (class 2604 OID 98392)
-- Name: system_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings ALTER COLUMN id SET DEFAULT nextval('public.system_settings_id_seq'::regclass);


--
-- TOC entry 2949 (class 2604 OID 97092)
-- Name: ticket_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys ALTER COLUMN id SET DEFAULT nextval('public.ticket_keys_id_seq'::regclass);


--
-- TOC entry 2944 (class 2604 OID 97010)
-- Name: tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets ALTER COLUMN id SET DEFAULT nextval('public.tickets_id_seq'::regclass);


--
-- TOC entry 2947 (class 2604 OID 97036)
-- Name: user_organizations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations ALTER COLUMN id SET DEFAULT nextval('public.user_organizations_id_seq'::regclass);


--
-- TOC entry 2938 (class 2604 OID 96920)
-- Name: users tg_user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN tg_user_id SET DEFAULT nextval('public.users_tg_user_id_seq'::regclass);


--
-- TOC entry 3015 (class 2606 OID 97497)
-- Name: action_logs action_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_pkey PRIMARY KEY (id);


--
-- TOC entry 2969 (class 2606 OID 96865)
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- TOC entry 3019 (class 2606 OID 97712)
-- Name: api_retry_queue api_retry_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue
    ADD CONSTRAINT api_retry_queue_pkey PRIMARY KEY (id);


--
-- TOC entry 3011 (class 2606 OID 97455)
-- Name: broadcast_deliveries broadcast_deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_pkey PRIMARY KEY (id);


--
-- TOC entry 3009 (class 2606 OID 97431)
-- Name: broadcasts broadcasts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_pkey PRIMARY KEY (id);


--
-- TOC entry 3007 (class 2606 OID 97410)
-- Name: calendar_rules calendar_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calendar_rules
    ADD CONSTRAINT calendar_rules_pkey PRIMARY KEY (id);


--
-- TOC entry 3021 (class 2606 OID 98239)
-- Name: escalations escalations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_pkey PRIMARY KEY (id);


--
-- TOC entry 3005 (class 2606 OID 97133)
-- Name: file_attachments file_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_pkey PRIMARY KEY (id);


--
-- TOC entry 2984 (class 2606 OID 96946)
-- Name: gs_keys gs_keys_key_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_key_number_key UNIQUE (key_number);


--
-- TOC entry 2986 (class 2606 OID 96944)
-- Name: gs_keys gs_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_pkey PRIMARY KEY (id);


--
-- TOC entry 2988 (class 2606 OID 96959)
-- Name: manager_assignments manager_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_pkey PRIMARY KEY (id);


--
-- TOC entry 3040 (class 2606 OID 106484)
-- Name: max_messenger_data max_messenger_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT max_messenger_data_pkey PRIMARY KEY (id);


--
-- TOC entry 2999 (class 2606 OID 97081)
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- TOC entry 3017 (class 2606 OID 97541)
-- Name: notification_events notification_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_pkey PRIMARY KEY (id);


--
-- TOC entry 3035 (class 2606 OID 98418)
-- Name: nps_responses nps_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses
    ADD CONSTRAINT nps_responses_pkey PRIMARY KEY (id);


--
-- TOC entry 2971 (class 2606 OID 96870)
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (inn);


--
-- TOC entry 2976 (class 2606 OID 97894)
-- Name: staff_members staff_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_pkey PRIMARY KEY (id);


--
-- TOC entry 3027 (class 2606 OID 98398)
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (id);


--
-- TOC entry 3001 (class 2606 OID 97094)
-- Name: ticket_keys ticket_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_pkey PRIMARY KEY (id);


--
-- TOC entry 2993 (class 2606 OID 97015)
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);


--
-- TOC entry 3013 (class 2606 OID 98087)
-- Name: broadcast_deliveries uq_broadcast_user_delivery; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT uq_broadcast_user_delivery UNIQUE (broadcast_id, user_id);


--
-- TOC entry 3042 (class 2606 OID 106488)
-- Name: max_messenger_data uq_max_messenger_max_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT uq_max_messenger_max_user_id UNIQUE (max_user_id);


--
-- TOC entry 3044 (class 2606 OID 106486)
-- Name: max_messenger_data uq_max_messenger_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT uq_max_messenger_user_id UNIQUE (user_id);


--
-- TOC entry 3003 (class 2606 OID 97096)
-- Name: ticket_keys uq_ticket_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT uq_ticket_key UNIQUE (ticket_id, key_id);


--
-- TOC entry 2990 (class 2606 OID 97937)
-- Name: manager_assignments uq_user_org_assignment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT uq_user_org_assignment UNIQUE (user_id, organization_inn);


--
-- TOC entry 2995 (class 2606 OID 98027)
-- Name: user_organizations uq_user_organization; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT uq_user_organization UNIQUE (user_id, organization_inn);


--
-- TOC entry 2997 (class 2606 OID 97038)
-- Name: user_organizations user_organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_pkey PRIMARY KEY (id);


--
-- TOC entry 2980 (class 2606 OID 96924)
-- Name: users users_phone_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_phone_number_key UNIQUE (phone_number);


--
-- TOC entry 2982 (class 2606 OID 97844)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 3028 (class 1259 OID 98429)
-- Name: idx_nps_type_responded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nps_type_responded ON public.nps_responses USING btree (survey_type, responded_at);


--
-- TOC entry 3029 (class 1259 OID 98428)
-- Name: idx_nps_user_responded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nps_user_responded ON public.nps_responses USING btree (user_id, responded_at);


--
-- TOC entry 3022 (class 1259 OID 98251)
-- Name: ix_escalations_is_resolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_escalations_is_resolved ON public.escalations USING btree (is_resolved);


--
-- TOC entry 3023 (class 1259 OID 98250)
-- Name: ix_escalations_ticket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_escalations_ticket_id ON public.escalations USING btree (ticket_id);


--
-- TOC entry 3036 (class 1259 OID 106496)
-- Name: ix_max_messenger_data_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_max_chat_id ON public.max_messenger_data USING btree (max_chat_id);


--
-- TOC entry 3037 (class 1259 OID 106495)
-- Name: ix_max_messenger_data_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_max_user_id ON public.max_messenger_data USING btree (max_user_id);


--
-- TOC entry 3038 (class 1259 OID 106494)
-- Name: ix_max_messenger_data_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_user_id ON public.max_messenger_data USING btree (user_id);


--
-- TOC entry 3030 (class 1259 OID 98427)
-- Name: ix_nps_responses_responded_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_responded_at ON public.nps_responses USING btree (responded_at);


--
-- TOC entry 3031 (class 1259 OID 98426)
-- Name: ix_nps_responses_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_sent_at ON public.nps_responses USING btree (sent_at);


--
-- TOC entry 3032 (class 1259 OID 98425)
-- Name: ix_nps_responses_survey_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_survey_type ON public.nps_responses USING btree (survey_type);


--
-- TOC entry 3033 (class 1259 OID 98424)
-- Name: ix_nps_responses_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_user_id ON public.nps_responses USING btree (user_id);


--
-- TOC entry 2972 (class 1259 OID 106503)
-- Name: ix_staff_members_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_members_max_chat_id ON public.staff_members USING btree (max_chat_id);


--
-- TOC entry 2973 (class 1259 OID 97721)
-- Name: ix_staff_members_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_members_max_user_id ON public.staff_members USING btree (max_user_id) WHERE (max_user_id IS NOT NULL);


--
-- TOC entry 2974 (class 1259 OID 97819)
-- Name: ix_staff_members_tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_members_tg_user_id ON public.staff_members USING btree (tg_user_id);


--
-- TOC entry 3024 (class 1259 OID 98405)
-- Name: ix_system_settings_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_settings_category ON public.system_settings USING btree (category);


--
-- TOC entry 3025 (class 1259 OID 98404)
-- Name: ix_system_settings_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_system_settings_key ON public.system_settings USING btree (key);


--
-- TOC entry 2991 (class 1259 OID 98254)
-- Name: ix_tickets_is_escalated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_is_escalated ON public.tickets USING btree (is_escalated);


--
-- TOC entry 2977 (class 1259 OID 97719)
-- Name: ix_users_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_max_user_id ON public.users USING btree (max_user_id) WHERE (max_user_id IS NOT NULL);


--
-- TOC entry 2978 (class 1259 OID 97820)
-- Name: ix_users_tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_tg_user_id ON public.users USING btree (tg_user_id);


--
-- TOC entry 3066 (class 2606 OID 98062)
-- Name: action_logs action_logs_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_staff_id_fkey FOREIGN KEY (staff_id) REFERENCES public.staff_members(id);


--
-- TOC entry 3067 (class 2606 OID 97508)
-- Name: action_logs action_logs_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);


--
-- TOC entry 3065 (class 2606 OID 98050)
-- Name: action_logs action_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3070 (class 2606 OID 98101)
-- Name: api_retry_queue api_retry_queue_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue
    ADD CONSTRAINT api_retry_queue_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3064 (class 2606 OID 97458)
-- Name: broadcast_deliveries broadcast_deliveries_broadcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_broadcast_id_fkey FOREIGN KEY (broadcast_id) REFERENCES public.broadcasts(id);


--
-- TOC entry 3063 (class 2606 OID 98088)
-- Name: broadcast_deliveries broadcast_deliveries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3062 (class 2606 OID 98074)
-- Name: broadcasts broadcasts_created_by_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_created_by_staff_id_fkey FOREIGN KEY (created_by_staff_id) REFERENCES public.staff_members(id);


--
-- TOC entry 3072 (class 2606 OID 98245)
-- Name: escalations escalations_resolved_by_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_resolved_by_staff_id_fkey FOREIGN KEY (resolved_by_staff_id) REFERENCES public.staff_members(id) ON DELETE SET NULL;


--
-- TOC entry 3071 (class 2606 OID 98240)
-- Name: escalations escalations_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 3060 (class 2606 OID 97134)
-- Name: file_attachments file_attachments_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id);


--
-- TOC entry 3061 (class 2606 OID 97552)
-- Name: file_attachments file_attachments_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 3048 (class 2606 OID 97948)
-- Name: gs_keys gs_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3050 (class 2606 OID 97982)
-- Name: manager_assignments manager_assignments_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.staff_members(id);


--
-- TOC entry 3049 (class 2606 OID 96967)
-- Name: manager_assignments manager_assignments_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- TOC entry 3051 (class 2606 OID 97938)
-- Name: manager_assignments manager_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3075 (class 2606 OID 106489)
-- Name: max_messenger_data max_messenger_data_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT max_messenger_data_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 3057 (class 2606 OID 97557)
-- Name: messages messages_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 3069 (class 2606 OID 97542)
-- Name: notification_events notification_events_related_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_related_ticket_id_fkey FOREIGN KEY (related_ticket_id) REFERENCES public.tickets(id);


--
-- TOC entry 3068 (class 2606 OID 98038)
-- Name: notification_events notification_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3074 (class 2606 OID 98419)
-- Name: nps_responses nps_responses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses
    ADD CONSTRAINT nps_responses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 3045 (class 2606 OID 98004)
-- Name: staff_members staff_members_backup_manager_1_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_backup_manager_1_id_fkey FOREIGN KEY (backup_manager_1_id) REFERENCES public.staff_members(id);


--
-- TOC entry 3046 (class 2606 OID 98015)
-- Name: staff_members staff_members_backup_manager_2_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_backup_manager_2_id_fkey FOREIGN KEY (backup_manager_2_id) REFERENCES public.staff_members(id);


--
-- TOC entry 3073 (class 2606 OID 98399)
-- Name: system_settings system_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.staff_members(id);


--
-- TOC entry 3058 (class 2606 OID 97097)
-- Name: ticket_keys ticket_keys_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_key_id_fkey FOREIGN KEY (key_id) REFERENCES public.gs_keys(id);


--
-- TOC entry 3059 (class 2606 OID 97562)
-- Name: ticket_keys ticket_keys_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 3053 (class 2606 OID 97992)
-- Name: tickets tickets_assigned_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_assigned_staff_id_fkey FOREIGN KEY (assigned_staff_id) REFERENCES public.staff_members(id) ON DELETE SET NULL;


--
-- TOC entry 3052 (class 2606 OID 97021)
-- Name: tickets tickets_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- TOC entry 3054 (class 2606 OID 97958)
-- Name: tickets tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 3055 (class 2606 OID 97041)
-- Name: user_organizations user_organizations_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- TOC entry 3056 (class 2606 OID 98028)
-- Name: user_organizations user_organizations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 3047 (class 2606 OID 97970)
-- Name: users users_default_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_default_manager_id_fkey FOREIGN KEY (default_manager_id) REFERENCES public.staff_members(id);


-- Completed on 2026-03-10 14:17:44

--
-- PostgreSQL database dump complete
--

