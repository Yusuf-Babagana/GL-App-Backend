"""
Push-notification tests: the right person is pushed, with the right deep-link data,
when something happens in the app. Run:  python manage.py test market.test_notifications
"""
from unittest.mock import MagicMock, patch

from chat.models import Conversation
from globalink_core import notify
from .test_escrow import Base, User

SELLER_TOKEN = "ExponentPushToken[seller-device]"
BUYER_TOKEN = "ExponentPushToken[buyer-device]"


class NotificationTests(Base):
    def setUp(self):
        super().setUp()
        User.objects.filter(pk=self.seller.pk).update(push_token=SELLER_TOKEN)
        User.objects.filter(pk=self.buyer.pk).update(push_token=BUYER_TOKEN)
        self.seller.refresh_from_db()
        self.buyer.refresh_from_db()
        p = patch("globalink_core.notify._send_push")
        self.push = p.start()
        self.addCleanup(p.stop)

    def pushes_to(self, token):
        return [c.args for c in self.push.call_args_list if c.args[0] == token]

    def test_seller_and_buyer_are_pushed_when_an_order_is_paid(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.pay()
        seller_push = self.pushes_to(SELLER_TOKEN)
        buyer_push = self.pushes_to(BUYER_TOKEN)
        self.assertEqual(len(seller_push), 1)
        self.assertEqual(seller_push[0][1], "New order received")
        self.assertEqual(seller_push[0][3]["order_id"], order.id)
        self.assertEqual(seller_push[0][3]["type"], "order")
        self.assertEqual(len(buyer_push), 1)
        self.assertEqual(buyer_push[0][1], "Payment successful")

    def test_buyer_is_pushed_when_the_seller_dispatches(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.pay()
        self.push.reset_mock()
        self.dispatch(order)
        pushes = self.pushes_to(BUYER_TOKEN)
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][1], "Your order is on its way")
        self.assertEqual(pushes[0][3]["order_id"], order.id)
        self.assertEqual(self.pushes_to(SELLER_TOKEN), [])

    def test_chat_message_pushes_the_other_person_only_and_sends_no_email(self):
        convo = Conversation.objects.create(buyer=self.buyer, seller=self.seller)
        from django.core import mail
        r = self.b.post(f"/api/chat/conversations/{convo.id}/messages/send/", {"text": "Is this available?"}, format="json")
        self.assertIn(r.status_code, (200, 201), r.data)
        pushes = self.pushes_to(SELLER_TOKEN)
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][2], "Is this available?")
        self.assertEqual(pushes[0][3], {"type": "chat", "conversation_id": convo.id})
        self.assertEqual(self.pushes_to(BUYER_TOKEN), [])
        self.assertEqual(mail.outbox, [])

    def test_user_without_a_token_is_skipped_quietly(self):
        User.objects.filter(pk=self.seller.pk).update(push_token=None)
        with self.captureOnCommitCallbacks(execute=True):
            self.pay()  # must not raise
        self.assertEqual(self.pushes_to(SELLER_TOKEN), [])


class DeadTokenTests(Base):
    def test_token_is_cleared_when_expo_says_device_not_registered(self):
        User.objects.filter(pk=self.buyer.pk).update(push_token=BUYER_TOKEN)
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}
        with patch("globalink_core.notify.requests.post", return_value=resp):
            notify._send_push(BUYER_TOKEN, "t", "b", {})
        self.buyer.refresh_from_db()
        self.assertIsNone(self.buyer.push_token)
