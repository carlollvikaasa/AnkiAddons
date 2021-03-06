# Anki Simulator Add-on for Anki
#
# Copyright (C) 2020  GiovanniHenriksen https://github.com/giovannihenriksen
# Copyright (C) 2020  Aristotelis P. https://glutanimate.com/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see https://www.gnu.org/licenses/.

from datetime import date, timedelta
from random import randint
from typing import Optional, List, Dict, Union

from .collection_simulator import (
    CARD_STATE_NEW,
    CARD_STATE_LEARNING,
    CARD_STATE_YOUNG,
    CARD_STATE_MATURE,
    CARD_STATE_RELEARN,
    DATE_ARRAY_TYPE,
    CARD_STATES_TYPE,
)


class ReviewSimulator:
    def __init__(
        self,
        date_array: DATE_ARRAY_TYPE,
        days_to_simulate: int,
        new_cards_per_day: int,
        interval_modifier: int,
        max_reviews_per_day: int,
        learning_steps: List[int],
        lapse_steps: List[int],
        graduating_interval: int,
        new_lapse_interval: int,
        max_interval: int,
        percentages_correct_for_learning_steps: List[int],
        percentages_correct_for_lapse_steps: List[int],
        chance_right_young: int,
        chance_right_mature: int,
    ):
        self.dateArray: DATE_ARRAY_TYPE = date_array
        self.daysToSimulate: int = days_to_simulate
        self.newCardsPerDay: int = new_cards_per_day
        self.intervalModifier: int = interval_modifier
        self.maxReviewsPerDay: int = max_reviews_per_day
        self.learningSteps: List[int] = learning_steps
        self.lapseSteps: List[int] = lapse_steps
        self.graduatingInterval: int = graduating_interval
        self.newLapseInterval: int = new_lapse_interval
        self.maxInterval: int = max_interval

        self._chance_right: Dict[CARD_STATES_TYPE, Union[int, List[int]]] = {
            CARD_STATE_NEW: percentages_correct_for_learning_steps,
            CARD_STATE_LEARNING: percentages_correct_for_learning_steps,
            CARD_STATE_RELEARN: percentages_correct_for_lapse_steps,
            CARD_STATE_YOUNG: chance_right_young,
            CARD_STATE_MATURE: chance_right_mature,
        }

    def reviewCorrect(self, state: CARD_STATES_TYPE, step: int) -> bool:
        randNumber = randint(1, 100)
        chance_right = self._chance_right[state]
        if isinstance(chance_right, (list, tuple)):
            chance_right = chance_right[step]
        return not (randNumber <= 100 - chance_right * 100)

    def nextRevInterval(
        self, current_interval: int, delay: int, ease_factor: int
    ) -> int:
        baseHardInterval = (current_interval + delay // 4) * 1.2
        constrainedHardInterval = max(
            baseHardInterval * self.intervalModifier, current_interval + 1
        )  # Hard interval needs
        # to be calculated to determine 'Normal' Interval, because new interval can not be lower than the hard interval
        baseGoodInterval = (current_interval + delay // 2) * (ease_factor / 100)
        constrainedGoodInterval = max(
            baseGoodInterval * self.intervalModifier, constrainedHardInterval + 1
        )
        return int(min(constrainedGoodInterval, self.maxInterval))

    def simulate(self, controller=None) -> Optional[List[Dict[str, Union[str, int]]]]:
        dayIndex = 0

        while dayIndex < len(self.dateArray):

            if controller:
                controller.day_processed(dayIndex)

            reviewNumber = 0
            daysToAdd = None
            idsDoneToday: List[int] = []
            # some cards may be postponed to the next day. We need to remove them from
            # the current day:
            removeList = []

            while reviewNumber < len(self.dateArray[dayIndex]):
                if controller and controller.do_cancel:
                    return None

                card = self.dateArray[dayIndex][reviewNumber]

                # Postpone reviews > max reviews per day to the next day:
                if (
                    card.state == CARD_STATE_YOUNG
                    or card.state == CARD_STATE_MATURE
                    and card.id not in idsDoneToday
                ):
                    if len(idsDoneToday) + 1 > self.maxReviewsPerDay:
                        if (dayIndex + 1) < self.daysToSimulate:
                            card.delay += 1
                            self.dateArray[dayIndex + 1].append(card)
                        removeList.append(reviewNumber)
                        reviewNumber += 1
                        continue
                    idsDoneToday.append(card.id)

                reviewCorrect = self.reviewCorrect(card.state, card.step)

                if reviewCorrect:
                    if (
                        card.state == CARD_STATE_NEW
                        or card.state == CARD_STATE_LEARNING
                    ):
                        if card.step < len(self.learningSteps) - 1:
                            # Unseen/learning card was correct and will become/remain a learning card.
                            card.state = CARD_STATE_LEARNING
                            card.step = card.step + 1
                            daysToAdd = int(self.learningSteps[card.step] / 1440)
                        else:
                            # Learning card was correct and will become a young/mature card.
                            card.ivl = self.graduatingInterval
                            if self.graduatingInterval >= 21:
                                card.state = CARD_STATE_MATURE
                            else:
                                card.state = CARD_STATE_YOUNG
                            daysToAdd = card.ivl
                    elif card.state == CARD_STATE_RELEARN:
                        if card.step < len(self.lapseSteps) - 1:
                            # Relearn card was correct and will remain a relearn card.
                            card.state = CARD_STATE_RELEARN
                            card.step = card.step + 1
                            daysToAdd = int(self.lapseSteps[card.step] / 1440)
                        else:
                            # Relearn card was correct and will become a young/mature card.
                            if card.ivl >= 21:
                                card.state = CARD_STATE_MATURE
                            else:
                                card.state = CARD_STATE_YOUNG
                            daysToAdd = card.ivl
                    elif card.state == CARD_STATE_YOUNG:
                        # Young card was correct and might become a mature card.
                        card.ivl = self.nextRevInterval(card.ivl, card.delay, card.ease)
                        card.delay = 0
                        if card.ivl >= 21:
                            card.state = CARD_STATE_MATURE
                        daysToAdd = card.ivl
                    elif card.state == CARD_STATE_MATURE:
                        # Mature card was correct and will remain a mature card.
                        card.ivl = self.nextRevInterval(card.ivl, card.delay, card.ease)
                        card.delay = 0
                        daysToAdd = card.ivl
                else:
                    if (
                        card.state == CARD_STATE_NEW
                        or card.state == CARD_STATE_LEARNING
                    ):
                        # New/learning card was incorrect and will become/remain a learning card.
                        card.state = CARD_STATE_LEARNING
                        card.step = 0
                        daysToAdd = int(self.learningSteps[0] / 1440)
                    elif card.state == CARD_STATE_RELEARN:
                        # Relearn card was incorrect and will remain a relearn card.
                        card.state = CARD_STATE_RELEARN
                        card.step = 0
                        daysToAdd = int(self.lapseSteps[0] / 1440)
                    elif (
                        card.state == CARD_STATE_YOUNG
                        or card.state == CARD_STATE_MATURE
                    ):
                        # Young/mature card was incorrect and will become a relearn card.
                        card.state = CARD_STATE_RELEARN
                        card.step = 0
                        card.delay = 0
                        card.ease = max(card.ease - 20, 130)
                        newInterval = max(
                            int(card.ivl * self.newLapseInterval), 1
                        )  # 1 is the minimum interval
                        card.ivl = newInterval
                        daysToAdd = int(self.lapseSteps[0] / 1440)

                if (
                    daysToAdd is not None
                    and (dayIndex + daysToAdd) < self.daysToSimulate
                ):
                    self.dateArray[dayIndex + daysToAdd].append(card)

                reviewNumber += 1

            # We will now remove all postponed reviews from their original day:
            for index in sorted(removeList, reverse=True):
                del self.dateArray[dayIndex][index]

            dayIndex += 1

        today = date.today()

        return [
            {"x": (today + timedelta(days=index)).isoformat(), "y": len(reviews)}
            for index, reviews in enumerate(self.dateArray)
        ]  # Returns the number of reviews for each day
