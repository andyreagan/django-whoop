"""Django signals emitted by the webhook receiver.

``event_received`` fires for every authenticated POST to the receiver view.
Connect a handler to drive ingest:

.. code-block:: python

    from django.dispatch import receiver
    from whoop.signals import event_received
    from whoop.webhooks import process_event

    @receiver(event_received)
    def on_event(sender, payload, **kwargs):
        process_event(payload)  # or hand off to celery / a queue

Sender is ``None`` (signal is namespace-only). The ``payload`` keyword carries
the parsed JSON body exactly as WHOOP sent it. WHOOP expects a 2xx within a
second and retries failures five times over ~an hour — if processing is
heavier than that, hand off to a queue rather than processing inline.
"""

import django.dispatch

event_received = django.dispatch.Signal()
