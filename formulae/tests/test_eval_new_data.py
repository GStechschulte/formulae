import pytest

import numpy as np
import pandas as pd

from formulae.eval import EvalEnvironment
from formulae.parser import Parser
from formulae.scanner import Scanner
from formulae.terms import Variable, Call, Term, Model
from formulae.design_matrices import design_matrices


@pytest.fixture(scope="module")
def data():
    from os.path import dirname, join

    data_dir = join(dirname(__file__), "data")
    data = pd.read_csv(join(data_dir, "original.csv"))
    return data


@pytest.fixture(scope="module")
def data2():
    from os.path import dirname, join

    data_dir = join(dirname(__file__), "data")
    data = pd.read_csv(join(data_dir, "new.csv"))
    return data


def test_term_new_data_numeric():
    data = pd.DataFrame({"x": [10, 10, 10]})
    var_expr = Parser(Scanner("x").scan(False)).parse()
    var_term = Variable(var_expr.name.lexeme, var_expr.level)
    var_term.set_type(data)
    var_term.set_data()
    assert (var_term.data["value"].T == [10, 10, 10]).all()
    data = pd.DataFrame({"x": [1, 2, 3]})
    assert (var_term.eval_new_data(data).T == [1, 2, 3]).all()


def test_call_new_data_numeric_stateful_transform():
    # The center() transformation remembers the value of the mean
    # of the first dataset passed, which is 10.
    eval_env = EvalEnvironment.capture(0)
    data = pd.DataFrame({"x": [10, 10, 10]})
    call_term = Call(Parser(Scanner("center(x)").scan(False)).parse())
    call_term.set_type(data, eval_env)
    call_term.set_data()
    assert (call_term.data["value"].T == [0, 0, 0]).all()
    data = pd.DataFrame({"x": [1, 2, 3]})
    assert (call_term.eval_new_data(data).T == [-9.0, -8.0, -7.0]).all()


def test_term_new_data_categoric():
    data = pd.DataFrame({"x": ["A", "B", "C"]})

    # Full rank encoding
    var_expr = Parser(Scanner("x").scan(False)).parse()
    var_term = Variable(var_expr.name.lexeme, var_expr.level)
    var_term.set_type(data)
    var_term.set_data(encoding=True)
    assert (np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) == var_term.data["value"]).all()

    data = pd.DataFrame({"x": ["B", "C"]})
    assert (var_term.eval_new_data(data) == np.array([[0, 1, 0], [0, 0, 1]])).all()

    # It remembers it saw "A", "B", and "C", but not "D".
    # So when you pass a new level, it raises a ValueError.
    with pytest.raises(ValueError):
        data = pd.DataFrame({"x": ["B", "C", "D"]})
        var_term.eval_new_data(data)

    # The same with reduced encoding
    data = pd.DataFrame({"x": ["A", "B", "C"]})
    var_expr = Parser(Scanner("x").scan(False)).parse()
    var_term = Variable(var_expr.name.lexeme, var_expr.level)
    var_term.set_type(data)
    var_term.set_data()
    assert (np.array([[0, 0], [1, 0], [0, 1]]) == var_term.data["value"]).all()

    data = pd.DataFrame({"x": ["A", "C"]})
    assert (var_term.eval_new_data(data) == np.array([[0, 0], [0, 1]])).all()

    # It remembers it saw "A", "B", and "C", but not "D".
    # So when you pass a new level, it raises a ValueError.
    with pytest.raises(ValueError):
        data = pd.DataFrame({"x": ["B", "C", "D"]})
        var_term.eval_new_data(data)


def test_call_new_data_categoric_stateful_transform():
    eval_env = EvalEnvironment.capture(0)
    data = pd.DataFrame({"x": [1, 2, 3]})

    # Full rank encoding
    call_term = Call(Parser(Scanner("C(x)").scan(False)).parse())
    call_term.set_type(data, eval_env)
    call_term.set_data(encoding=True)
    assert (np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) == call_term.data["value"]).all()

    data = pd.DataFrame({"x": [2, 3]})
    assert (call_term.eval_new_data(data) == np.array([[0, 1, 0], [0, 0, 1]])).all()

    with pytest.raises(ValueError):
        data = pd.DataFrame({"x": [2, 3, 4]})
        call_term.eval_new_data(data)

    # The same with reduced encoding
    data = pd.DataFrame({"x": [1, 2, 3]})
    call_term = Call(Parser(Scanner("C(x)").scan(False)).parse())
    call_term.set_type(data, eval_env)
    call_term.set_data()
    assert (np.array([[0, 0], [1, 0], [0, 1]]) == call_term.data["value"]).all()

    data = pd.DataFrame({"x": [1, 3]})
    assert (call_term.eval_new_data(data) == np.array([[0, 0], [0, 1]])).all()

    # It remembers it saw "A", "B", and "C", but not "D".
    # So when you pass a new level, it raises a ValueError.
    with pytest.raises(ValueError):
        data = pd.DataFrame({"x": [2, 3, 4]})
        call_term.eval_new_data(data)


def test_model_numeric_common(data, data2):
    dm = design_matrices("y ~ np.exp(x) + z", data)
    common2 = dm.common._evaluate_new_data(data2)
    assert np.allclose(np.exp(data2["x"]), common2["np.exp(x)"].flatten())
    assert np.allclose(data2["z"], common2["z"].flatten())

    dm = design_matrices("y ~ center(x) + scale(z)", data)
    common1 = dm.common
    common2 = dm.common._evaluate_new_data(data2)

    # First, assert stateful transforms remember the original parameter values
    t1_mean1 = common1.model.terms[1].components[0].stateful_transform.mean
    t1_mean2 = common2.model.terms[1].components[0].stateful_transform.mean
    assert np.allclose(t1_mean1, 0, atol=1)
    assert np.allclose(t1_mean1, t1_mean2)

    t2_mean1 = common1.model.terms[2].components[0].stateful_transform.mean
    t2_mean2 = common2.model.terms[2].components[0].stateful_transform.mean
    t2_std1 = common1.model.terms[2].components[0].stateful_transform.std
    t2_std2 = common2.model.terms[2].components[0].stateful_transform.std
    assert np.allclose(t2_mean1, 0, atol=1)
    assert np.allclose(t2_std1, 1, atol=1)
    assert np.allclose(t2_mean1, t2_mean2)
    assert np.allclose(t2_std1, t2_std2)

    # Second, assert variables have been transformed using original parameter values
    assert np.allclose(common2["center(x)"].flatten(), data2["x"] - t1_mean1)
    assert np.allclose(common2["scale(z)"].flatten(), (data2["z"] - t2_mean1) / t2_std1)


def test_model_categoric_common(data, data2):
    dm = design_matrices("y ~ g1", data)
    common1 = dm.common
    common2 = common1._evaluate_new_data(data2)
    arr = np.array([0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0])

    assert common1.terms_info["g1"] == common2.terms_info["g1"]
    assert np.allclose(common2["g1"].flatten(), arr)

    dm = design_matrices("y ~ 0 + C(u)", data)
    common1 = dm.common
    common2 = common1._evaluate_new_data(data2)
    arr = np.array(
        [
            [1, 0, 0],
            [0, 1, 0],
            [0, 1, 0],
            [0, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [0, 0, 1],
            [0, 1, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [0, 0, 1],
            [0, 0, 1],
            [1, 0, 0],
            [0, 0, 1],
            [0, 1, 0],
        ]
    )
    assert common1.terms_info["C(u)"] == common2.terms_info["C(u)"]
    assert (common2["C(u)"] == arr).all()


def test_model_numeric_group(data, data2):
    dm = design_matrices("y ~ (x|g1)", data)
    group1 = dm.group
    group2 = group1._evaluate_new_data(data2)

    d1 = {k: v for k, v in group1.terms_info["1|g1"].items() if k not in ["idxs", "Xi", "Ji"]}
    d2 = {k: v for k, v in group2.terms_info["1|g1"].items() if k not in ["idxs", "Xi", "Ji"]}
    assert d1 == d2

    d1 = {k: v for k, v in group1.terms_info["x|g1"].items() if k not in ["idxs", "Xi", "Ji"]}
    d2 = {k: v for k, v in group2.terms_info["x|g1"].items() if k not in ["idxs", "Xi", "Ji"]}
    assert d1 == d2


def test_model_categoric_group(data, data2):
    dm = design_matrices("y ~ (0 + g1|g2)", data)
    group1 = dm.group
    group2 = group1._evaluate_new_data(data2)

    d1 = {k: v for k, v in group1.terms_info["g1[X]|g2"].items() if k not in ["idxs", "Xi", "Ji"]}
    d2 = {k: v for k, v in group2.terms_info["g1[X]|g2"].items() if k not in ["idxs", "Xi", "Ji"]}
    assert d1 == d2

    d1 = {k: v for k, v in group1.terms_info["g1[Y]|g2"].items() if k not in ["idxs", "Xi", "Ji"]}
    d2 = {k: v for k, v in group2.terms_info["g1[Y]|g2"].items() if k not in ["idxs", "Xi", "Ji"]}
    assert d1 == d2

    arr = np.array(
        [
            [1, 0],
            [0, 0],
            [0, 0],
            [0, 0],
            [0, 0],
            [0, 1],
            [1, 0],
            [0, 1],
            [0, 0],
            [0, 0],
            [0, 0],
            [0, 1],
            [1, 0],
            [0, 0],
            [1, 0],
            [0, 0],
        ]
    )

    assert (group2["g1[X]|g2"] == arr).all()

    arr = np.array(
        [
            [0, 0],
            [0, 1],
            [1, 0],
            [0, 1],
            [1, 0],
            [0, 0],
            [0, 0],
            [0, 0],
            [1, 0],
            [0, 1],
            [1, 0],
            [0, 0],
            [0, 0],
            [0, 1],
            [0, 0],
            [0, 1],
        ]
    )

    assert (group2["g1[Y]|g2"] == arr).all()
