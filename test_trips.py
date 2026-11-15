import unittest
from trips import trip_details
class TripTests(unittest.TestCase):
 def test_multi_day_first_exit(self):
  x=trip_details({'dates':['2030-10-23','2030-10-24','2030-10-25'],'stations':['苏州吴中站','小海站','南通西站','顾山站']},'去南通大学交流')
  self.assertEqual(x['event'],'至20301025共3天去南通大学交流')
  self.assertEqual(x['destination'],'小海站')
 def test_single_day(self):
  self.assertEqual(trip_details({'dates':['2030-10-29'],'stations':[]},'去扬州大学交流')['event'],'去扬州大学交流')
if __name__=='__main__':unittest.main()
