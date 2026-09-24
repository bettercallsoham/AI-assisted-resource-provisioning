import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from preprocessing import chronological_split, make_sequences


def test_sequences_preserve_order():
    sequences, targets = make_sequences([1, 2, 3, 4], 2)
    assert sequences == [[1, 2], [2, 3]]
    assert targets == [3, 4]


def test_split_is_chronological():
    frame = pd.DataFrame({"timestamp": range(10)})
    train, validation, test = chronological_split(frame)
    assert train.iloc[-1, 0] < validation.iloc[0, 0] < test.iloc[0, 0]