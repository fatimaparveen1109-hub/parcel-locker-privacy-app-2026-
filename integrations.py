"""Adapters for the QR system and the physical locker controller. Both are SIMULATED today.
When the real QR provider and controller details exist, replace ONLY the bodies of these classes.
Do not invent endpoints: wait for the real specification."""


class LockerController:
    mode = "Simulated"

    def unlock(self, hub_id, locker_id):
        """TODO real controller: send the unlock command and return True when the door really opened."""
        return True

    def door_closed(self, hub_id, locker_id):
        """TODO real controller: read the door sensor. In the demo a button confirms 'door closed'."""
        return True


class QRProvider:
    mode = "Built-in (HMAC tokens, hashed in the database)"
    # TODO: if the other group's QR system is used later, call it from services/qr.py issue()/verify().


LOCKER = LockerController()
QR_PROVIDER = QRProvider()
