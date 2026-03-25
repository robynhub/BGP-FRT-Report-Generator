--
-- PostgreSQL database dump
--

\restrict fxv4EcUlWyWdgcnYCA1khcxtmmVBSobMahMahqAgusK8fPrcalwKYWAeSog01Cn

-- Dumped from database version 13.23 (Debian 13.23-0+deb11u1)
-- Dumped by pg_dump version 13.23 (Debian 13.23-0+deb11u1)

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: current_rib; Type: TABLE; Schema: public; Owner: bgpmon
--

CREATE TABLE public.current_rib (
    peer_ip inet NOT NULL,
    afi smallint NOT NULL,
    safi smallint NOT NULL,
    prefix inet NOT NULL,
    next_hop inet,
    as_path text,
    origin_as bigint,
    communities text,
    local_pref integer,
    med integer,
    origin text,
    last_seen timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.current_rib OWNER TO bgpmon;

--
-- Name: rib_stage; Type: TABLE; Schema: public; Owner: bgpmon
--

CREATE TABLE public.rib_stage (
    peer_ip text NOT NULL,
    afi text NOT NULL,
    safi text NOT NULL,
    prefix text NOT NULL,
    next_hop text,
    as_path text,
    origin_as text,
    communities text,
    local_pref text,
    med text,
    origin text
);


ALTER TABLE public.rib_stage OWNER TO bgpmon;

--
-- Name: current_rib current_rib_pkey; Type: CONSTRAINT; Schema: public; Owner: bgpmon
--

ALTER TABLE ONLY public.current_rib
    ADD CONSTRAINT current_rib_pkey PRIMARY KEY (peer_ip, afi, safi, prefix);


--
-- Name: current_rib_origin_as_idx; Type: INDEX; Schema: public; Owner: bgpmon
--

CREATE INDEX current_rib_origin_as_idx ON public.current_rib USING btree (origin_as);


--
-- Name: current_rib_prefix_gist; Type: INDEX; Schema: public; Owner: bgpmon
--

CREATE INDEX current_rib_prefix_gist ON public.current_rib USING gist (prefix inet_ops);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

GRANT USAGE ON SCHEMA public TO bgpmon;


--
-- PostgreSQL database dump complete
--

\unrestrict fxv4EcUlWyWdgcnYCA1khcxtmmVBSobMahMahqAgusK8fPrcalwKYWAeSog01Cn

