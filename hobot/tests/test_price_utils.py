import unittest
from service.macro_trading.utils.price_utils import adjust_to_tick_size

class TestPriceUtils(unittest.TestCase):
    def test_etf_tick_sizes(self):
        # Case 1: Under 2000 won (1 won tick)
        self.assertEqual(adjust_to_tick_size(1500), 1500)
        self.assertEqual(adjust_to_tick_size(1500.1), 1500)
        self.assertEqual(adjust_to_tick_size(1500.9), 1501)
        
        # Case 2: Over 2000 won (5 won tick)
        self.assertEqual(adjust_to_tick_size(2000), 2000)
        self.assertEqual(adjust_to_tick_size(2001), 2000) # Rounds down
        self.assertEqual(adjust_to_tick_size(2002), 2000) # Rounds down
        self.assertEqual(adjust_to_tick_size(2003), 2005) # Rounds up
        self.assertEqual(adjust_to_tick_size(10233), 10235) # Rounds to nearest 5
        self.assertEqual(adjust_to_tick_size(10232), 10230) # Rounds to nearest 5
        self.assertEqual(adjust_to_tick_size(50000), 50000)
        
        # Specific user case
        # "etf라서 호가단위 5인데 왜 에러가 나는거지?"
        # Assuming the invalid price was something like 10233
        self.assertEqual(adjust_to_tick_size(10233), 10235)

if __name__ == '__main__':
    unittest.main()
