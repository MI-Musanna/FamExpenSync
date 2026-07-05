import unittest
import os
from sqlalchemy import create_engine
import database
import models
from app import app

class FamilyTrackerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_engine = create_engine('sqlite:///family_tracker_test.db')
        database.db_session.configure(bind=cls.test_engine)
        database.Base.metadata.bind = cls.test_engine

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key-123'
        self.client = app.test_client()
        database.Base.metadata.create_all(bind=self.test_engine)
        models.seed_data()

    def tearDown(self):
        database.db_session.remove()
        database.Base.metadata.drop_all(bind=self.test_engine)
        
    @classmethod
    def tearDownClass(cls):
        # উইন্ডোজ ফাইল লক রিলিজ করার জন্য সেশন রিমুভ ও ইঞ্জিন ডিসপোজ করা বাধ্যতামূলক
        database.db_session.remove()
        cls.test_engine.dispose() 
        if os.path.exists('family_tracker_test.db'):
            os.remove('family_tracker_test.db')

    def test_core_dashboard_loads(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Family Expense Portal', response.data)

    def test_secure_pin_handshake_success(self):
        response = self.client.post('/verify_pin', data=dict(member_id='4', pin='1234'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'success', response.data)

    def test_secure_pin_handshake_failure(self):
        response = self.client.post('/verify_pin', data=dict(member_id='4', pin='0000'))
        self.assertEqual(response.status_code, 401)

    def test_input_validation_negative_amount_rejection(self):
        with self.client.session_transaction() as sess:
            sess['auth_member_4'] = True
        response = self.client.post('/add', data=dict(
            member_id='4', category_id='1', amount='-250.00', description='Hacker attack', date='2026-07-04'
        ), follow_redirects=True)
        self.assertIn(b'Amount must be greater than zero', response.data)

if __name__ == '__main__':
    unittest.main()