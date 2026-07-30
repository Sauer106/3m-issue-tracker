"""Read-only integration with CA Service Desk Manager (CA SDM / Broadcom).

STATUS: scaffold only. Blocked on API access from Eric Metzger — we still need the
CA SDM version (SOAP web services vs the 14.1+ REST API), confirmation that the
web-services port is reachable from this server, and a read-only service account.
Until config.ini's [servicedesk] base_url is set, is_enabled() returns False and the
app shows nothing ServiceDesk-related.

Intended flow (CA SDM SOAP web services, the classic interface):
  1. login(username, password) -> a session id (SID)
  2. doSelect on the "cr" (request/incident) object filtered by ref_num, which is
     the ServiceDesk Ticket # we already store on issues/projects. Pull status,
     last activity, and summary.
  3. logout(SID).
On CA SDM 14.1+ the REST API (/caisd-rest/) is simpler and preferred if available.

When access lands: implement fetch_ticket(ref_num) below, then surface the result
as a read-only, ServiceDesk-tagged panel on the issue/project detail page (a blue
"ServiceDesk" badge, matching the existing history badge styling).
"""
import db


def is_enabled():
    try:
        return bool(db.get_config()["servicedesk"].get("base_url", "").strip())
    except KeyError:
        return False


def fetch_ticket(ref_num):
    """Return {status, last_activity, summary} for a ServiceDesk ref_num, or None.

    Not implemented yet — see module docstring. Guarded by is_enabled() so nothing
    calls this until the integration is configured.
    """
    raise NotImplementedError("ServiceDesk integration is pending API access.")
