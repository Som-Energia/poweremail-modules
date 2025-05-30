# -*- coding: utf-8 -*-
from osv import osv
from tools.translate import _
from signaturit_sdk.signaturit_client import SignaturitClient
from tools import config
import netsvc
import tools
import base64
import tempfile
import os


def get_signaturit_client():
    client = SignaturitClient(
        config['signaturit_token'],
        config.get('signaturit_production', False)
    )
    return client


class PoweremailCore(osv.osv):

    _inherit = 'poweremail.core_accounts'

    def send_mail_certificat(self, cr, uid, ids, addresses, subject='', body=None, payload=None, context=None):
        """
        :return: 'True' si s'ha pogut enviar el email, altrament un missatge de error
        """
        def parse_body_html(pem_body_html, pem_body_text):
            html = pem_body_text if not pem_body_html else pem_body_html
            if (
                html and html.strip()[0] != '<' and
                "<br/>" not in html and
                "<br>" not in html
            ):
                html = html.replace('\n', '<br/>')
            return html

        client = get_signaturit_client()
        if body is None:
            body = {}
        if context is None:
            context = {}
        if payload is None:
            payload = {}

        if addresses is None or not addresses.get("To"):
            raise osv.except_osv(_(u"Error"), _(u"No s'ha especificat cap destinatari"))
        try:
            addresses_list = self.get_ids_from_dict(addresses)
        except Exception as error:
            return error

        # Subject
        subject = subject or context.get('subject', '') or ''

        # Body
        body_html = parse_body_html(
            pem_body_html=tools.ustr(body.get('html', '')),
            pem_body_text=tools.ustr(body.get('text', ''))
        )

        # Main Recivers
        recipients = []
        for reciver in addresses_list.get('To', []):
            recipients.append({
                'name': reciver,
                'email': reciver
            })

        # Other params
        params = dict()

        # Other recivers
        params['recipients'] = {}
        for key in addresses_list:
            key = key.lower()
            if key in ["to", "from", "all"]:
                continue
            if not addresses_list.get(key):
                continue
            if key not in params['recipients']:
                params['recipients'][key] = []
            for email_id in addresses_list[key]:
                params['recipients'][key].append({
                    'name': email_id,
                    'email': email_id
                })

        # Certified email type
        request_type = self.pool.get("res.config").get(cr, uid, "signaturit_email_request_type", "open_document")
        params['type'] = request_type

        # Attachments
        documents = []
        tmp_dir = tempfile.mkdtemp(prefix='poweremail-signaturit-')
        for fname, fdata in payload.iteritems():
            fname = fname.replace("/", "")  # Pels que posen barres al numero de factura...
            document_path = os.path.join(tmp_dir, fname)
            with open(document_path, 'w') as tmp_document:
                tmp_document.write(base64.b64decode(fdata))
                documents.append(document_path)

        response = client.create_email(
            files=documents,
            recipients=recipients,
            subject=subject,
            body=body_html,
            params=params
        )
        res = False
        if "id" in response and context.get("poweremail_id"):
            self.pool.get("poweremail.mailbox").write(cr, uid, context.get("poweremail_id"), {
                'certificat_signature_id': response.get("id"),
                'certificat_state': "email_processed"
            })
            res = True
        if "error" in response:
            res = response.get('error_message', response['error'])
        return res

    def get_mail_audit_trail(self, cr, uid, ids, audit_trail_id, context=None):
        if context is None:
            context = {}

        res = False
        client = get_signaturit_client()
        mail_json = client.get_email(audit_trail_id)
        certificates = []
        if mail_json:
            certificates = mail_json.get('certificates', [])
        if not certificates:
            raise osv.except_osv(_("Error"), _("No hi ha certificats"))
        for certificat in certificates:  # només n'hi hauria d'haber 1
            certificates_id = certificat.get('id', None)
            res = client.download_email_audit_trail(audit_trail_id, certificates_id)
        return res


PoweremailCore()
