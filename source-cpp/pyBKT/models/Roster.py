from pyBKT.models import Model
from enum import Enum
import numpy as np

class StateType(Enum):
    DEFAULT_STATE = 1
    UNMASTERED = 2
    MASTERED = 3

class Roster:
    def __init__(self, students, skill, mastery_state = 0.95, track_progress = False, model = None):
        self.model = model if model is not None else Model()
        self.students = {}
        self.mastery_state = mastery_state
        self.track_progress = track_progress
        self.skill = skill
        if isinstance(students, int):
            self.add_students(list(range(1, students + 1)))
        elif isinstance(students, list):
            self.add_students(students)

    # STATE BASED METHODS

    def reset_state(self, student_name):
        self.students[student_name] = State.DEFAULT_STATE

    def reset_states(self):
        for s in self.students:
            self.reset_state(s)

    def get_state(self, student_name):
        return self.students[student_name]

    def get_states(self):
        return self.students
        
    def update_state(self, student_name, correct, **kwargs):
        self.students[student_name].update(correct, kwargs) 
        return self.get_state(student_name)

    def update_states(self, corrects, **kwargs):
        for s in corrects:
            self.update_state(s, corrects[s], **kwargs)
        return self.get_states()

    # STUDENT BASED METHODS

    def add_student(self, student_name, initial_state = StateType.DEFAULT_STATE):
        self.students[student_name] = State(initial_state, self)

    def add_students(self, student_names, initial_states = StateType.DEFAULT_STATE):
        if not isinstance(initial_states, list):
            initial_states = [initial_states] * len(student_names)
        for i, s in enumerate(student_names):
            self.add_student(s, initial_states[i])

    def remove_student(self, student_name):
        del self.students[student_name]

    def remove_students(self, student_names):
        for s in student_names:
            self.remove_student(s)

    # MISCELLANEOUS FUNCTIONS

    def get_model(self):
        return self.model

    def set_model(self, model):
        self.model = model

    def get_mastery_state(self):
        return self.mastery_state

    def set_mastery_state(self, mastery_state):
        self.mastery_state = mastery_state
        for s in self.students:
            self.students[student_name].refresh()

    # NATIVE PYTHON FUNCTIONS
    def __repr__(self):
        return 'Roster(%s, %s, %s, %s, %s)' % (repr(len(self.students)), repr(self.skill), 
                                               repr(self.mastery_state), repr(self.track_progress), 
                                               repr(self.model))

class State:
    def __init__(self, initial_state, roster):
        self.state_type = initial_state
        self.roster = roster
        if self.roster.model.fit_model and self.roster.skill in self.roster.model.fit_model:
            self.current_state = {'correct_prediction': -1, 'state_prediction': self.roster.model.fit_model[self.roster.skill]['prior']}
        else:
            self.current_state = {'correct_prediction': -1, 'state_prediction': -1}
        self.tracked_states = []

    def update(self, correct, kwargs):
        if isinstance(correct, int):
            data = self.process_data(np.array([correct]), kwargs)
        elif isinstance(correct, np.ndarray):
            data = self.process_data(correct, kwargs)
        else:
            raise ValueError("need to pass int or np.ndarray")
        correct_predictions, state_predictions = self.predict(self.roster.model, self.roster.skill, data, self.current_state)
        self.current_state['correct_prediction'] = correct_predictions[-2]
        self.current_state['state_prediction'] = state_predictions[-1]
        
        if self.roster.track_progress:
            self.tracked_states.append(dict(self.current_state))
        self.refresh()

    def process_data(self, corrects, kwargs):
        multilearn, multigs = [kwargs.get(t, False) for t in ('multilearn', 'multigs')]
        gs_ref = self.roster.model.fit_model[self.roster.skill]['gs_names']
        resource_ref = self.roster.model.fit_model[self.roster.skill]['resource_names']
        corrects = np.append(corrects, [-1])
        data = corrects + 1
        lengths = np.array([len(corrects)], dtype=np.int64)
        starts = np.array([1], dtype=np.int64)
        
        if multilearn:
            resources = np.array(kwargs['multilearn'].apply(lambda x: resource_ref[x]))
        else:
            resources = np.ones(len(data), dtype=np.int64)

        if multigs:
            data_ref = np.array(kwargs['multigs']).apply(lambda x: gs_ref[x])
            data_temp = np.zeros((len(gs_ref), len(corrects)))
            for i in range(len(data_temp[0])):
                data_temp[data_ref[i]][i] = data[i]
            data = np.asarray(data_temp,dtype='int32')
        else:
            data = np.asarray([data], dtype='int32')

        Data = {'starts': starts, 'lengths': lengths, 'resources': resources, 'data': data}
        return Data

    def predict(self, model, skill, data, state):
        if state['state_prediction'] > 0:
            old_prior = model.fit_model[self.roster.skill]['pi_0']
            model.fit_model[self.roster.skill]['pi_0'] = np.array([[1 - state['state_prediction']], [state['state_prediction']]])
            model.fit_model[self.roster.skill]['prior'] = model.fit_model[self.roster.skill]['pi_0'][1][0]
        correct_predictions, state_predictions = model._predict(model.fit_model[skill], data)
        model.fit_model[self.roster.skill]['pi_0'] = old_prior if state['state_prediction'] > 0 else model.fit_model[self.roster.skill]['pi_0']
        model.fit_model[self.roster.skill]['prior'] = model.fit_model[self.roster.skill]['pi_0'][1][0]
        return correct_predictions, state_predictions[1]

    def refresh(self):
        if self.current_state['state_prediction'] == -1:
            self.state_type = StateType.DEFAULT_STATE
        elif self.current_state['state_prediction'] >= self.roster.mastery_state:
            self.state_type = StateType.MASTERED
        else:
            self.state_type = StateType.UNMASTERED

    def __repr__(self):
        stype = repr(self.state_type)
        stype = stype[stype.index('<') + 1: stype.index(':')]
        return '%s with mastery probability: %f and correctness probability: %f' % (stype, 
                self.current_state['state_prediction'], self.current_state['correct_prediction'])
