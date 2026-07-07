--
-- PostgreSQL database dump
--

\restrict nzB3q6vHP8fCCjhBFAsbwdwsfJpZ1gXGNb1v5994ZlZ7OPVXhQkdxLc5vagu1Ax

-- Dumped from database version 14.23 (Ubuntu 14.23-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.23 (Ubuntu 14.23-0ubuntu0.22.04.1)

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
    'PHONE_CHANGE_REJECTED',
    'TICKET_TAKEN',
    'ticket_taken'
);


--
-- Name: broadcaststatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.broadcaststatus AS ENUM (
    'DRAFT',
    'SENDING',
    'COMPLETED',
    'FAILED'
);


--
-- Name: deliverymethod; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.deliverymethod AS ENUM (
    'TELEGRAM',
    'EMAIL',
    'NONE'
);


--
-- Name: deliverystatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.deliverystatus AS ENUM (
    'PENDING',
    'DELIVERED',
    'FAILED'
);


--
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
-- Name: eventstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventstatus AS ENUM (
    'SCHEDULED',
    'SENT',
    'FAILED',
    'CANCELLED'
);


--
-- Name: eventtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventtype AS ENUM (
    'RENEWAL_REMINDER_30',
    'RENEWAL_REMINDER_7',
    'NPS_SURVEY'
);


--
-- Name: filetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.filetype AS ENUM (
    'PDF',
    'IMAGE',
    'DOCUMENT',
    'OTHER'
);


--
-- Name: keyconflictstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.keyconflictstatus AS ENUM (
    'NONE',
    'PENDING_REVIEW',
    'RESOLVED'
);


--
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
-- Name: registrationstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.registrationstatus AS ENUM (
    'PENDING',
    'ACTIVE',
    'REJECTED',
    'UNDER_REVIEW'
);


--
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
-- Name: retrystatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.retrystatus AS ENUM (
    'pending',
    'success',
    'failed',
    'PENDING',
    'SUCCESS',
    'FAILED'
);


--
-- Name: sendertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sendertype AS ENUM (
    'USER',
    'STAFF',
    'SYSTEM'
);


--
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
-- Name: settingdatatype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.settingdatatype AS ENUM (
    'integer',
    'json',
    'chat_id',
    'user_id'
);


--
-- Name: staffrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.staffrole AS ENUM (
    'MANAGER',
    'TECHNICAL_SUPPORT',
    'DUTY_ENGINEER',
    'ADMINISTRATOR'
);


--
-- Name: subscriptionstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.subscriptionstatus AS ENUM (
    'ACTIVE',
    'EXPIRED',
    'NONE'
);


--
-- Name: surveytype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.surveytype AS ENUM (
    'loyalty',
    'service_quality',
    'LOYALTY',
    'SERVICE_QUALITY'
);


--
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
-- Name: tickettype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.tickettype AS ENUM (
    'INVOICE',
    'TECHNICAL_SUPPORT',
    'RENEWAL',
    'phone_change',
    'PHONE_CHANGE',
    'NEW',
    'IN_PROGRESS',
    'consultation',
    'CONSULTATION',
    'KEY_CONFLICT'
);


--
-- Name: uploadertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.uploadertype AS ENUM (
    'USER',
    'STAFF'
);


--
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
-- Name: action_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.action_logs_id_seq OWNED BY public.action_logs.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
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
-- Name: api_retry_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.api_retry_queue_id_seq OWNED BY public.api_retry_queue.id;


--
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
-- Name: broadcast_deliveries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcast_deliveries_id_seq OWNED BY public.broadcast_deliveries.id;


--
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
-- Name: broadcasts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcasts_id_seq OWNED BY public.broadcasts.id;


--
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
-- Name: calendar_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.calendar_rules_id_seq OWNED BY public.calendar_rules.id;


--
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
-- Name: escalations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.escalations_id_seq OWNED BY public.escalations.id;


--
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
-- Name: file_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_attachments_id_seq OWNED BY public.file_attachments.id;


--
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
-- Name: gs_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gs_keys_id_seq OWNED BY public.gs_keys.id;


--
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
-- Name: manager_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manager_assignments_id_seq OWNED BY public.manager_assignments.id;


--
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
-- Name: max_messenger_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.max_messenger_data_id_seq OWNED BY public.max_messenger_data.id;


--
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
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
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
-- Name: notification_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notification_events_id_seq OWNED BY public.notification_events.id;


--
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
-- Name: nps_responses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nps_responses_id_seq OWNED BY public.nps_responses.id;


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    inn character varying(12) NOT NULL,
    organization_name character varying(256),
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT ck_organizations_inn_format CHECK ((((inn)::text ~ '^[0-9]{10}$'::text) OR ((inn)::text ~ '^[0-9]{12}$'::text)))
);


--
-- Name: staff_members_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_members_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
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
    max_chat_id bigint,
    is_estimate_tech_specialist boolean DEFAULT false NOT NULL,
    is_working_today boolean DEFAULT true NOT NULL
);


--
-- Name: COLUMN staff_members.is_estimate_tech_specialist; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_members.is_estimate_tech_specialist IS 'Сметный тех. специалист — получает заявки типа Консультация';


--
-- Name: COLUMN staff_members.is_working_today; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_members.is_working_today IS 'Сотрудник доступен сегодня — если False, не получает новые заявки';


--
-- Name: staff_members_tg_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_members_tg_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: staff_members_tg_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.staff_members_tg_user_id_seq OWNED BY public.staff_members.tg_user_id;


--
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
-- Name: system_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_settings_id_seq OWNED BY public.system_settings.id;


--
-- Name: ticket_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticket_keys (
    id integer NOT NULL,
    ticket_id integer NOT NULL,
    key_id integer NOT NULL,
    added_at timestamp without time zone NOT NULL
);


--
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
-- Name: ticket_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ticket_keys_id_seq OWNED BY public.ticket_keys.id;


--
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
    CONSTRAINT ck_tickets_escalation_level CHECK ((escalation_level = ANY (ARRAY[0, 1, 2, 3])))
);


--
-- Name: COLUMN tickets.escalation_task_reminder_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.escalation_task_reminder_id IS 'ID Celery задачи напоминания';


--
-- Name: COLUMN tickets.escalation_task_escalation_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.escalation_task_escalation_id IS 'ID Celery задачи эскалации';


--
-- Name: COLUMN tickets.is_escalated; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.is_escalated IS 'Флаг эскалированной заявки';


--
-- Name: COLUMN tickets.old_phone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.old_phone IS 'Old phone number for phone change requests';


--
-- Name: COLUMN tickets.new_phone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.new_phone IS 'New phone number for phone change requests';


--
-- Name: COLUMN tickets.resolution_comment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.resolution_comment IS 'Resolution comment for closed tickets';


--
-- Name: COLUMN tickets.queue_notification_sent_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tickets.queue_notification_sent_at IS 'Timestamp when queue notification was sent (prevents duplicate notifications)';


--
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
-- Name: tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tickets_id_seq OWNED BY public.tickets.id;


--
-- Name: user_organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_organizations (
    id integer NOT NULL,
    organization_inn character varying(12) NOT NULL,
    added_at timestamp without time zone NOT NULL,
    user_id bigint NOT NULL
);


--
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
-- Name: user_organizations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_organizations_id_seq OWNED BY public.user_organizations.id;


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
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
-- Name: users_tg_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_tg_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_tg_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_tg_user_id_seq OWNED BY public.users.tg_user_id;


--
-- Name: action_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs ALTER COLUMN id SET DEFAULT nextval('public.action_logs_id_seq'::regclass);


--
-- Name: api_retry_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue ALTER COLUMN id SET DEFAULT nextval('public.api_retry_queue_id_seq'::regclass);


--
-- Name: broadcast_deliveries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries ALTER COLUMN id SET DEFAULT nextval('public.broadcast_deliveries_id_seq'::regclass);


--
-- Name: broadcasts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts ALTER COLUMN id SET DEFAULT nextval('public.broadcasts_id_seq'::regclass);


--
-- Name: calendar_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calendar_rules ALTER COLUMN id SET DEFAULT nextval('public.calendar_rules_id_seq'::regclass);


--
-- Name: escalations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations ALTER COLUMN id SET DEFAULT nextval('public.escalations_id_seq'::regclass);


--
-- Name: file_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments ALTER COLUMN id SET DEFAULT nextval('public.file_attachments_id_seq'::regclass);


--
-- Name: gs_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys ALTER COLUMN id SET DEFAULT nextval('public.gs_keys_id_seq'::regclass);


--
-- Name: manager_assignments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments ALTER COLUMN id SET DEFAULT nextval('public.manager_assignments_id_seq'::regclass);


--
-- Name: max_messenger_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data ALTER COLUMN id SET DEFAULT nextval('public.max_messenger_data_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: notification_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events ALTER COLUMN id SET DEFAULT nextval('public.notification_events_id_seq'::regclass);


--
-- Name: nps_responses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses ALTER COLUMN id SET DEFAULT nextval('public.nps_responses_id_seq'::regclass);


--
-- Name: staff_members tg_user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members ALTER COLUMN tg_user_id SET DEFAULT nextval('public.staff_members_tg_user_id_seq'::regclass);


--
-- Name: system_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings ALTER COLUMN id SET DEFAULT nextval('public.system_settings_id_seq'::regclass);


--
-- Name: ticket_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys ALTER COLUMN id SET DEFAULT nextval('public.ticket_keys_id_seq'::regclass);


--
-- Name: tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets ALTER COLUMN id SET DEFAULT nextval('public.tickets_id_seq'::regclass);


--
-- Name: user_organizations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations ALTER COLUMN id SET DEFAULT nextval('public.user_organizations_id_seq'::regclass);


--
-- Name: users tg_user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN tg_user_id SET DEFAULT nextval('public.users_tg_user_id_seq'::regclass);


--
-- Name: action_logs action_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: api_retry_queue api_retry_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue
    ADD CONSTRAINT api_retry_queue_pkey PRIMARY KEY (id);


--
-- Name: broadcast_deliveries broadcast_deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_pkey PRIMARY KEY (id);


--
-- Name: broadcasts broadcasts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_pkey PRIMARY KEY (id);


--
-- Name: calendar_rules calendar_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calendar_rules
    ADD CONSTRAINT calendar_rules_pkey PRIMARY KEY (id);


--
-- Name: escalations escalations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_pkey PRIMARY KEY (id);


--
-- Name: file_attachments file_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_pkey PRIMARY KEY (id);


--
-- Name: gs_keys gs_keys_key_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_key_number_key UNIQUE (key_number);


--
-- Name: gs_keys gs_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_pkey PRIMARY KEY (id);


--
-- Name: manager_assignments manager_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_pkey PRIMARY KEY (id);


--
-- Name: max_messenger_data max_messenger_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT max_messenger_data_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: notification_events notification_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_pkey PRIMARY KEY (id);


--
-- Name: nps_responses nps_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses
    ADD CONSTRAINT nps_responses_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (inn);


--
-- Name: staff_members staff_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (id);


--
-- Name: ticket_keys ticket_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_pkey PRIMARY KEY (id);


--
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);


--
-- Name: broadcast_deliveries uq_broadcast_user_delivery; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT uq_broadcast_user_delivery UNIQUE (broadcast_id, user_id);


--
-- Name: max_messenger_data uq_max_messenger_max_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT uq_max_messenger_max_user_id UNIQUE (max_user_id);


--
-- Name: max_messenger_data uq_max_messenger_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT uq_max_messenger_user_id UNIQUE (user_id);


--
-- Name: ticket_keys uq_ticket_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT uq_ticket_key UNIQUE (ticket_id, key_id);


--
-- Name: manager_assignments uq_user_org_assignment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT uq_user_org_assignment UNIQUE (user_id, organization_inn);


--
-- Name: user_organizations uq_user_organization; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT uq_user_organization UNIQUE (user_id, organization_inn);


--
-- Name: user_organizations user_organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_pkey PRIMARY KEY (id);


--
-- Name: users users_phone_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_phone_number_key UNIQUE (phone_number);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_nps_type_responded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nps_type_responded ON public.nps_responses USING btree (survey_type, responded_at);


--
-- Name: idx_nps_user_responded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nps_user_responded ON public.nps_responses USING btree (user_id, responded_at);


--
-- Name: ix_escalations_is_resolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_escalations_is_resolved ON public.escalations USING btree (is_resolved);


--
-- Name: ix_escalations_ticket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_escalations_ticket_id ON public.escalations USING btree (ticket_id);


--
-- Name: ix_max_messenger_data_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_max_chat_id ON public.max_messenger_data USING btree (max_chat_id);


--
-- Name: ix_max_messenger_data_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_max_user_id ON public.max_messenger_data USING btree (max_user_id);


--
-- Name: ix_max_messenger_data_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_messenger_data_user_id ON public.max_messenger_data USING btree (user_id);


--
-- Name: ix_nps_responses_responded_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_responded_at ON public.nps_responses USING btree (responded_at);


--
-- Name: ix_nps_responses_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_sent_at ON public.nps_responses USING btree (sent_at);


--
-- Name: ix_nps_responses_survey_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_survey_type ON public.nps_responses USING btree (survey_type);


--
-- Name: ix_nps_responses_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_nps_responses_user_id ON public.nps_responses USING btree (user_id);


--
-- Name: ix_staff_members_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_members_max_chat_id ON public.staff_members USING btree (max_chat_id);


--
-- Name: ix_staff_members_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_members_max_user_id ON public.staff_members USING btree (max_user_id) WHERE (max_user_id IS NOT NULL);


--
-- Name: ix_staff_members_tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_members_tg_user_id ON public.staff_members USING btree (tg_user_id);


--
-- Name: ix_system_settings_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_settings_category ON public.system_settings USING btree (category);


--
-- Name: ix_system_settings_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_system_settings_key ON public.system_settings USING btree (key);


--
-- Name: ix_tickets_is_escalated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_is_escalated ON public.tickets USING btree (is_escalated);


--
-- Name: ix_users_max_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_max_user_id ON public.users USING btree (max_user_id) WHERE (max_user_id IS NOT NULL);


--
-- Name: ix_users_tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_tg_user_id ON public.users USING btree (tg_user_id);


--
-- Name: action_logs action_logs_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_staff_id_fkey FOREIGN KEY (staff_id) REFERENCES public.staff_members(id);


--
-- Name: action_logs action_logs_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);


--
-- Name: action_logs action_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: api_retry_queue api_retry_queue_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_retry_queue
    ADD CONSTRAINT api_retry_queue_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: broadcast_deliveries broadcast_deliveries_broadcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_broadcast_id_fkey FOREIGN KEY (broadcast_id) REFERENCES public.broadcasts(id);


--
-- Name: broadcast_deliveries broadcast_deliveries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcast_deliveries
    ADD CONSTRAINT broadcast_deliveries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: broadcasts broadcasts_created_by_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_created_by_staff_id_fkey FOREIGN KEY (created_by_staff_id) REFERENCES public.staff_members(id);


--
-- Name: escalations escalations_resolved_by_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_resolved_by_staff_id_fkey FOREIGN KEY (resolved_by_staff_id) REFERENCES public.staff_members(id) ON DELETE SET NULL;


--
-- Name: escalations escalations_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- Name: file_attachments file_attachments_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id);


--
-- Name: file_attachments file_attachments_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_attachments
    ADD CONSTRAINT file_attachments_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- Name: gs_keys gs_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gs_keys
    ADD CONSTRAINT gs_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: manager_assignments manager_assignments_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.staff_members(id);


--
-- Name: manager_assignments manager_assignments_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- Name: manager_assignments manager_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_assignments
    ADD CONSTRAINT manager_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: max_messenger_data max_messenger_data_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_messenger_data
    ADD CONSTRAINT max_messenger_data_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: messages messages_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- Name: notification_events notification_events_related_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_related_ticket_id_fkey FOREIGN KEY (related_ticket_id) REFERENCES public.tickets(id);


--
-- Name: notification_events notification_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_events
    ADD CONSTRAINT notification_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: nps_responses nps_responses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nps_responses
    ADD CONSTRAINT nps_responses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: staff_members staff_members_backup_manager_1_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_backup_manager_1_id_fkey FOREIGN KEY (backup_manager_1_id) REFERENCES public.staff_members(id);


--
-- Name: staff_members staff_members_backup_manager_2_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_backup_manager_2_id_fkey FOREIGN KEY (backup_manager_2_id) REFERENCES public.staff_members(id);


--
-- Name: system_settings system_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.staff_members(id);


--
-- Name: ticket_keys ticket_keys_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_key_id_fkey FOREIGN KEY (key_id) REFERENCES public.gs_keys(id);


--
-- Name: ticket_keys ticket_keys_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_keys
    ADD CONSTRAINT ticket_keys_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- Name: tickets tickets_assigned_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_assigned_staff_id_fkey FOREIGN KEY (assigned_staff_id) REFERENCES public.staff_members(id) ON DELETE SET NULL;


--
-- Name: tickets tickets_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- Name: tickets tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: user_organizations user_organizations_organization_inn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_organization_inn_fkey FOREIGN KEY (organization_inn) REFERENCES public.organizations(inn);


--
-- Name: user_organizations user_organizations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_organizations
    ADD CONSTRAINT user_organizations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users users_default_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_default_manager_id_fkey FOREIGN KEY (default_manager_id) REFERENCES public.staff_members(id);


--
-- PostgreSQL database dump complete
--

\unrestrict nzB3q6vHP8fCCjhBFAsbwdwsfJpZ1gXGNb1v5994ZlZ7OPVXhQkdxLc5vagu1Ax

