import ssl

from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend
from django.core.mail.utils import DNS_NAME


class UnverifiedSSLEmailBackend(DjangoSMTPBackend):
    """SMTP backend that skips TLS certificate verification.

    Use when the mail relay is an internal cluster service whose hostname
    does not match the certificate CN (e.g. a Kubernetes-internal Mailu front).
    Set EMAIL_SSL_NO_VERIFY=True in the environment to activate.
    """

    def open(self):
        if self.connection:
            return False

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        connection_params = {"local_hostname": DNS_NAME.get_fqdn()}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = ssl_context

        try:
            self.connection = self.connection_class(self.host, self.port, **connection_params)
            if not self.use_ssl:
                self.connection.ehlo()
                if self.use_tls:
                    self.connection.starttls(context=ssl_context)
                    self.connection.ehlo()
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise
