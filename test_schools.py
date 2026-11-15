import unittest
from schools import select_school

class SchoolTests(unittest.TestCase):
    def test_prefers_prominent_university_within_local_radius(self):
        candidates=[{'name':'地方学院','distance_m':1500}, {'name':'江苏大学','distance_m':9000,'tags':{'wikidata':'Q1'}}]
        self.assertEqual(select_school(candidates)['name'],'江苏大学')
    def test_distant_school_not_selected(self):
        self.assertIsNone(select_school([{'name':'远方大学','distance_m':100000}]))

if __name__=='__main__': unittest.main()
