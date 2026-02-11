import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import tkinter.font as tkfont
import json

# Optional: background image support
try:
    from PIL import Image, ImageTk, ImageEnhance  # type: ignore
except Exception:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

import csv
import random
import re
import os
import datetime
from typing import Dict, List, Optional, Any




# -------------------- TOOLTIP SUPPORT --------------------
TOOLTIPS_ENABLED = True  # Set to False to disable all hover tooltips.

class ToolTip:
    """Simple hover tooltip for Tkinter widgets."""

    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tipwindow = None
        self._after_id = None

        self.widget.bind("<Enter>", self._schedule)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def _schedule(self, event=None):
        self._unschedule()
        self._after_id = self.widget.after(self.delay, self.show)

    def _unschedule(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def show(self):
        if self.tipwindow is not None or not self.text:
            return

        tw = tk.Toplevel(self.widget)
        self.tipwindow = tw
        tw.wm_overrideredirect(True)

        label = tk.Label(
            tw,
            text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=6, ipady=3)

        tw.update_idletasks()

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        tip_w = tw.winfo_reqwidth()
        tip_h = tw.winfo_reqheight()

        screen_w = self.widget.winfo_screenwidth()
        screen_h = self.widget.winfo_screenheight()
        pad = 8

        if x + tip_w + pad > screen_w:
            x = max(pad, screen_w - tip_w - pad)

        if y + tip_h + pad > screen_h:
            y = self.widget.winfo_rooty() - tip_h - 6

        if y < pad:
            y = pad

        tw.wm_geometry(f"+{x}+{y}")

    def hide(self, event=None):
        self._unschedule()
        if self.tipwindow is not None:
            try:
                self.tipwindow.destroy()
            except Exception:
                pass
            self.tipwindow = None



def attach_tooltip(widget, text: str, delay: int = 500):
    """Attach a tooltip to a widget, respecting TOOLTIPS_ENABLED."""
    if not TOOLTIPS_ENABLED:
        return
    assert "ToolTip" in globals(), "ToolTip class is not defined yet."
    try:
        ToolTip(widget, text, delay=delay)
    except Exception:
        # Tooltips should never break the app
        pass



# -------------------- HELP CONTENT --------------------
HELP_TEXT = """Max Walker Cricket Simulator – Help

Main controls
- Series: Set up / manage a multi-Test series.
- Start Match: Begin a match with the currently selected teams.
- Edit Team 1 Order / Edit Team 2 Order: Change the batting order for each team.
- Simulate Over: Bowl the next over with the selected bowler.
- Declare Innings: End the current innings early (declaration).
- Exit Match: End the current match and return to setup.

Ball-by-ball
- Ball-by-ball: Toggle ball-by-ball ticker updates.
- Speed: Slow / Medium / Fast controls animation delay.

Tips
- Bowlers cannot bowl consecutive overs and have session/day limits.
- Retired Hurt batters can return on the next day of play.
"""

STARTUP_HOWTO_TEXT = """Welcome to Max Walker Cricket Game Simulator!

This game is modelled on the original Max Walker's Cricket Game which came out in the 80's.
It was a dice cricket game with historical teams. There were Batting & Bowling charts, 
Loose Ball cards and each day of the Test match required a new Match Conditions card to be drawn.
I've tried to include all of those dynamics in this computerised version. 

Quick start
1) Pick Team 1 and Team 2 by checking box next to player(or load historical or saved teams).
2) Your team must have at least 5 bowlers and one wicketkeeper.
3) You can filter the list by clicking the dropdowns.
4) You can also save your team to use in later games.
5) You can Edit Team Order to adjust batting order before the match.
6) You can choose to play either a Single Test or Series of 3 or 5 Tests.
7) Once you have made your selections click Start Match.
8) Once the match has commenced select a bowler, then click Simulate Over.
9) Bowlers are allowed a maximum of 2 overs per Session.
10) Use Declare Innings when you want to declare.
11) You have the ability to save scorecards and series statistics.

Tips
- The ball by ball ticker animation can be switched on or off, and its speed can be controlled.
- Team and players databases are saved_teams.csv & all_test_players.csv
- Full instructions: Help → Help.
"""
# -------------------- PLAYER CLASS --------------------
class Player:
    def __init__(self, name: str, country: str, bat: str, bowl: Optional[str], wk: bool = False):
        self.innings_declared = False
        self.name = name
        self.country = country
        self.batting_rating = bat
        self.bowling_rating = bowl
        self.is_wk = wk

        # Match stats
        self.runs = 0
        self.balls_faced = 0
        self.fours = 0
        self.sixes = 0
        self.how_out: str = ""  # scorecard dismissal text; blank until dismissed / innings ends
        self.wickets = 0
        self.overs_bowled = 0
        self.runs_conceded = 0

    def display(self) -> str:
        wk = " (WK)" if self.is_wk else ""
        bowl = self.bowling_rating if self.bowling_rating else "-"
        return f"{self.name}{wk} | Bat {self.batting_rating} | Bowl {bowl} | {self.country}"

    def reset_match_stats(self) -> None:
        self.runs = 0
        self.balls_faced = 0
        self.fours = 0
        self.sixes = 0
        self.how_out = ""
        self.wickets = 0
        self.overs_bowled = 0
        self.runs_conceded = 0


# -------------------- MATCH CLASS --------------------
class Match:
    def __init__(self, *args, **kwargs):
        # Batting milestone tracking (per innings)
        self._milestones_awarded = {}  # player -> set(milestone)
        # Hat-trick tracking (three bowler-attributed wickets in three consecutive balls)
        self._hattrick_bowler = None
        self._hattrick_count = 0
        self._last_ball_was_bowler_wicket = False
        self._last_wicket_bowler = None
        self.innings_declared = False

    # -------------------- DICE CHARTS --------------------
    # Indexing note: we roll 2d6 -> 2..12, so we pad indexes 0..1 with blanks.
    BATTING_CHART: Dict[str, List[Any]] = {
        "A": ["", ""] + ["*", "1", "4", "6", "4", "4", "6", "2", "3", "*", "Loose Ball"],
        "B": ["", ""] + ["2", "*", "6", "4", "3", "4", "4", "6", "3", "*", "Loose Ball"],
        "C": ["", ""] + ["*", "*", "6", "2", "3", "4", "4", "6", "3", "*", "Loose Ball"],
        "D": ["", ""] + ["*", "*", "4", "3", "6", "4", "3", "4", "*", "3", "Loose Ball"],
        "E": ["", ""] + ["*", "*", "1", "2", "3", "4", "4", "3", "*", "4", "Loose Ball"],
        "F": ["", ""] + ["0", "*", "3", "4", "2", "1", "2", "2", "*", "*", "Loose Ball"],
        "G": ["", ""] + ["3", "*", "0", "*", "1", "0", "2", "1", "*", "4", "Loose Ball"],
    }

    BOWLER_WICKET_CHART: Dict[str, List[Any]] = {
        "A": ["", ""] + ["No ball", "LBW", "Caught WK", "Caught", "Not out", "Bowled", "Not out", "Caught", "LBW", "Caught WK", "Loose Ball"],
        "B": ["", ""] + ["No ball", "LBW", "Caught", "Not out", "Not out", "Bowled", "Not out", "Caught WK", "Stumped WK", "LBW", "Loose Ball"],
        "C": ["", ""] + ["No ball", "Not out", "Stumped WK", "Not out", "Caught", "Not out", "Bowled", "Not out", "LBW", "Not out", "Loose Ball"],
        "D": ["", ""] + ["No ball", "Caught", "Bowled", "Not out", "Not out", "Not out", "Not out", "Caught", "LBW", "Not out", "Loose Ball"],
        "E": ["", ""] + ["No ball", "Caught", "Not out", "Caught", "Not out", "Not out", "Not out", "Not out", "Not out", "Bowled", "Loose Ball"],
    }

    # -------------------- LOOSE BALL CARDS --------------------
    # IMPORTANT:
    # Loose Ball must ALWAYS be returned as a dict (type="Loose Ball")
    # NEVER return "Loose Ball" as a string.
    LOOSE_BALL_CARDS: List[Dict[str, Any]] = [
        {"text": "Quick single - run out at bowler's end", "out": "striker", "method": "Run Out", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 2},
        {"text": "Wicketkeeper fails to take ball - 2 byes", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 2, "score_inc": 2},
        {"text": "Wicketkeeper fails to take ball - 4 byes", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 4, "score_inc": 4},
        {"text": "Bouncer edged to slips - caught", "out": "striker", "method": "Caught", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "No ball", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 1, "extras_runs": 1, "score_inc": 1, "extra_ball": True},
        {"text": "Batsman attempting 3rd run - run out 2 runs", "out": "striker", "method": "Run Out", "batsman_runs": 2, "bowler_runs": 2, "extras_runs": 0, "score_inc": 2},
        {"text": "Leg glance mistimed - caught", "out": "striker", "method": "Caught", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "Poor return to wicketkeeper - 2 overthrows", "out": None, "method": None, "batsman_runs": 2, "bowler_runs": 2, "extras_runs": 0, "score_inc": 2},
        {"text": "Hook shot - catch dropped, 2 runs", "out": None, "method": None, "batsman_runs": 2, "bowler_runs": 2, "extras_runs": 0, "score_inc": 2},
        {"text": "Batsman hit by bouncer - retired hurt", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0, "retired_hurt": True},
        {"text": "Leg glance - 4 leg byes", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 4, "score_inc": 4},
        {"text": "Leg glance - 4 runs", "out": None, "method": None, "batsman_runs": 4, "bowler_runs": 4, "extras_runs": 0, "score_inc": 4},
        {"text": "Bouncer edged to wicketkeeper - caught", "out": "striker", "method": "Caught", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "Hook shot - 6 runs", "out": None, "method": None, "batsman_runs": 6, "bowler_runs": 6, "extras_runs": 0, "score_inc": 6},
        {"text": "Bouncer edged - catch dropped", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "Silly mid-on - catch dropped", "out": None, "method": None, "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "Edged through slips - 4 runs", "out": None, "method": None, "batsman_runs": 4, "bowler_runs": 4, "extras_runs": 0, "score_inc": 4},
        {"text": "Edged to wicketkeeper - caught", "out": "striker", "method": "Caught", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "Ball keeps low - LBW", "out": "striker", "method": "LBW", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
        {"text": "Silly mid-on - caught", "out": "striker", "method": "Caught", "batsman_runs": 0, "bowler_runs": 0, "extras_runs": 0, "score_inc": 0},
    ]

    # -------------------- MATCH CONDITIONS CARDS --------------------
    # A "day" is 16 overs in this simulator (2 sessions of 8 overs).
    # Each condition can:
    # - shorten the day (overs_lost_start / overs_lost_end)
    # - cancel the day entirely (no_play=True)
    # - apply batting/bowling rating modifiers for specific over ranges within the day
    #
    # Modifiers: -1 makes a rating "worse" (e.g. B -> C). +1 makes it "better" (e.g. C -> B).
    # (This matches apply_rating_modifier() which shifts within RATINGS_ORDER.)
    DAY_OVERS = 16
    MAX_DAYS = 5

    MATCH_CONDITION_TEMPLATES: List[Dict[str, Any]] = [
        # Weighted "Normal conditions" (28x)
        {"text": "Normal conditions apply throughout the day.", "weight": 28,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "Wearing pitch and defensive batting assists bowlers. Reduce batsmen ratings by 1 for the last 8 overs.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 8, "bat": 0, "bowl": 0}, {"start": 9, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Midday rain affects pitch. Reduce each batsman rating by 1 for the last 8 overs.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 8, "bat": 0, "bowl": 0}, {"start": 9, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Overcast conditions favour bowlers for the first 5 overs. Reduce batsmen ratings by 1 for this period, then revert to normal conditions.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 5, "bat": -1, "bowl": 0}, {"start": 6, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "No play today - constant heavy rain.", "weight": 1,
         "overs_lost_start": DAY_OVERS, "overs_lost_end": 0, "no_play": True,
         "phases": []},

        {"text": "Rain prevents play all day.", "weight": 1,
         "overs_lost_start": DAY_OVERS, "overs_lost_end": 0, "no_play": True,
         "phases": []},

        {"text": "Conditions perfect for batting. Reduce each bowler's rating by 1 for the entire day's play.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        # NOTE: Spec says "first 8 overs assist bowlers" but then "reduce batsman rating for first 10 overs".
        # We follow the explicit reduction window: first 10 overs.
        {"text": "Overcast conditions assist bowlers for the first 8 overs. Reduce each batsman rating by 1 for the first 10 overs then normal conditions apply.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 10, "bat": -1, "bowl": 0}, {"start": 11, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "Rain delays the start of play by 8 overs. Pitch favours the bowlers for the rest of the day. Reduce each batsman rating by 1.", "weight": 1,
         "overs_lost_start": 8, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Hot conditions tiring for the bowlers. Reduce bowlers rating by 1 for the last 4 overs of the day.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 12, "bat": 0, "bowl": 0}, {"start": 13, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        {"text": "Bad light stops play three overs early. Play during the available time is under normal conditions.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 3, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "Ideal batting conditions. Reduce each bowler's rating by 1 for the whole day.", "weight": 2,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        {"text": "Good conditions for batting. Conditions normal for 8 overs, then reduce each bowler's rating by 1.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 8, "bat": 0, "bowl": 0}, {"start": 9, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        {"text": "Rain on pitch assists bowlers. Reduce each batsman rating by 1 for the entire day's play.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Rain delays play. 5 overs lost. Normal conditions apply once play commences.", "weight": 1,
         "overs_lost_start": 5, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "Fast pitch ideal for bowling team. Reduce each batsman rating by 1 for the entire day.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Pitch improving during the day. Normal conditions apply for the first 8 overs, then reduce bowlers ratings by 1 for the remainder of the day.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 8, "bat": 0, "bowl": 0}, {"start": 9, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        {"text": "Humid conditions favour the bowlers. Reduce each batsman rating by 1 for the entire day's play.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Rain delays start of play by 8 overs. Normal conditions apply once play commences.", "weight": 1,
         "overs_lost_start": 8, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "Afternoon rain affects the pitch and assists bowlers. Reduce batsman ratings by 1 for the last 4 overs.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 12, "bat": 0, "bowl": 0}, {"start": 13, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Weather conditions have made ideal batting. Reduce each bowler's rating by 1 for the entire day.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        {"text": "Hot weather tiring for the bowlers. Reduce bowlers rating by 1 for the last 8 overs.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 8, "bat": 0, "bowl": 0}, {"start": 9, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},

        {"text": "No play today. Incessant rain.", "weight": 1,
         "overs_lost_start": DAY_OVERS, "overs_lost_end": 0, "no_play": True,
         "phases": []},

        {"text": "Heavy overnight rain continuing today. No play for the entire day.", "weight": 1,
         "overs_lost_start": DAY_OVERS, "overs_lost_end": 0, "no_play": True,
         "phases": []},

        {"text": "Heavy rain falling. No play for the entire day.", "weight": 1,
         "overs_lost_start": DAY_OVERS, "overs_lost_end": 0, "no_play": True,
         "phases": []},

        {"text": "Rain delays play. 5 overs lost. Pitch favours bowlers for the first 5 overs. Reduce each batsman rating by 1.", "weight": 1,
         "overs_lost_start": 5, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 5, "bat": -1, "bowl": 0}, {"start": 6, "end": DAY_OVERS, "bat": 0, "bowl": 0}]},

        {"text": "Overnight rain seeped under the covers. Pitch favours bowlers for the whole day. Reduce each batsman rating by 1.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": DAY_OVERS, "bat": -1, "bowl": 0}]},

        {"text": "Good conditions for cricket, with pitch improving. Conditions normal for the first 8 overs, then reduce bowlers rating by 1.", "weight": 1,
         "overs_lost_start": 0, "overs_lost_end": 0, "no_play": False,
         "phases": [{"start": 1, "end": 8, "bat": 0, "bowl": 0}, {"start": 9, "end": DAY_OVERS, "bat": 0, "bowl": -1}]},
    ]

    # Flatten to a weighted "deck" for random draws.
    MATCH_CONDITIONS_DECK: List[Dict[str, Any]] = []
    for _c in MATCH_CONDITION_TEMPLATES:
        _w = int(_c.get("weight", 1) or 1)
        MATCH_CONDITIONS_DECK.extend([_c] * max(1, _w))
    RATINGS_ORDER = ["A", "B", "C", "D", "E", "F", "G"]

    def reset_innings_batting_stats(self) -> None:
        self.runs = 0
        self.balls_faced = 0
        self.fours = 0
        self.sixes = 0
        self.how_out = ""

    def reset_innings_bowling_stats(self) -> None:
        self.overs_bowled = 0
        self.runs_conceded = 0
        self.wickets = 0

    def __init__(self, team1: List[Player], team2: List[Player], gui: "CricketGUI"):
        self.team1 = team1
        self.team2 = team2
        self.gui = gui

        # Batting milestone tracking (per innings)
        self._milestones_awarded = {}  # player -> set(milestone)

        # Hat-trick tracking (three bowler-attributed wickets in three consecutive balls)
        self._hattrick_bowler = None
        self._hattrick_count = 0
        self._hattrick_pending_bowler = None  # bowler with 2-in-a-row wickets awaiting hat-trick ball
        self._last_ball_was_bowler_wicket = False
        self._last_wicket_bowler = None

        # Innings declaration flag (allows ending innings before 10 wickets)
        self.innings_declared = False

        # Retired hurt tracking
        # Players in this list are currently retired hurt and may return later (per your rules).
        self.retired_hurt_pending: List[Player] = []
        self.retired_hurt_returning: List[Player] = []
        # When True, returning retired-hurt players take priority over unused batsmen (from start of next day)
        self.retired_hurt_priority: bool = False


        # Cache wicketkeeper per innings (fallback if no explicit WK is marked)
        self._wk_name_by_innings: Dict[int, str] = {}

        self.innings = 1
        self.runs = 0
        self.wickets_taken = 0
        self.overs_completed = 0

        # Session tracking (used for per-session bowling limits)
        self.overs_per_session = 8
        self.session_overs_completed = 0
        self.session_number = 1

        self.last_bowler: Optional[str] = None
        self.current_batsmen: List[Player] = [team1[0], team1[1]]
        self.next_batsman_index = 2
        self.bowler: Optional[Player] = None

        # Bowling limits tracking
        self.bowler_overs_session: Dict[str, int] = {p.name: 0 for p in self.team2}
        self.bowler_overs_today: Dict[str, int] = {p.name: 0 for p in self.team2}

        self.match_over = False
        self.result_summary = None

        self.extras = 0
        self.extras_nb = 0   # No balls (included in extras)
        self.extras_b = 0    # Byes (included in extras)
        self.extras_lb = 0   # Leg byes (included in extras)
        self.extras_w = 0    # Wides (included in extras)

        # Store completed innings summaries (for scorecards / tabs later)
        # keys: innings number (1..4)
        self.innings_summaries: Dict[int, Dict[str, Any]] = {}
        self.innings_batting_team: Dict[int, int] = {1: 1}  # innings -> 1 (Team1) or 2 (Team2)
        self.follow_on_enforced = False
        self.follow_on_threshold = 200  # standard follow-on lead
        self.fow: List[tuple[int, int]] = []  # [(wicket_no, runs_at_fall)]
        self.current_over_legal_balls = 0

        # Reset retired-hurt tracking for the new innings (must never leak across innings/teams)
        self.retired_hurt_pending = []
        self.retired_hurt_returning = []
        self.retired_hurt_priority = False

        # Internal: track which session the bowling limits were last reset for
        self._limits_session_number = self.session_number

        # Match conditions / day tracking
        self.current_conditions: Optional[Dict[str, Any]] = None
        self.day_counter = 1
        self.current_day = 1  # day currently in play

        self.day_overs_target = self.DAY_OVERS  # base overs in a day
        self.day_overs_scheduled = self.DAY_OVERS  # may be reduced by conditions (lost overs / early finish)
        self.overs_in_day = 0  # overs actually bowled today (0..day_overs_scheduled)

        self.day_no_play = False
        self.day_overs_lost_start = 0
        self.day_overs_lost_end = 0

        self.start_new_day()


    def _get_wicketkeeper_name(self, fielding_team: List[Player]) -> str:
        """Return a stable wicketkeeper name for the current innings.

        Prefers an explicitly marked wicketkeeper (Player.is_wk).
        If none is marked, picks the first player as a deterministic fallback so
        display text remains consistent across the innings.
        """
        if self.innings in self._wk_name_by_innings:
            return self._wk_name_by_innings[self.innings]

        wk_player = next((p for p in fielding_team if getattr(p, "is_wk", False)), None)
        wk_name = wk_player.name if wk_player else (fielding_team[0].name if fielding_team else "the wicketkeeper")
        self._wk_name_by_innings[self.innings] = wk_name
        return wk_name

    
    def _set_dismissal(self, batsman: Player, method: str, fielding_team: List[Player], bowler: Optional[Player], *, fielder_name: Optional[str] = None, wk_name: Optional[str] = None) -> None:
        """Set scorecard-style dismissal text on the batsman."""
        m = (method or "").strip()
        ml = m.lower()
        bname = bowler.name if bowler else ""
        if ml == "caught wk":
            wk = wk_name or self._get_wicketkeeper_name(fielding_team)
            batsman.how_out = f"c {wk} b {bname}".strip()
        elif ml == "stumped wk":
            wk = wk_name or self._get_wicketkeeper_name(fielding_team)
            batsman.how_out = f"st {wk} b {bname}".strip()
        elif ml == "caught":
            f = fielder_name
            if not f:
                wk = wk_name or self._get_wicketkeeper_name(fielding_team)
                candidates = [p.name for p in fielding_team if p.name not in {bname, wk}]
                f = random.choice(candidates) if candidates else "a fielder"
            batsman.how_out = f"c {f} b {bname}".strip()
        elif ml == "lbw":
            batsman.how_out = f"lbw b {bname}".strip()
        elif ml == "bowled":
            batsman.how_out = f"b {bname}".strip()
        elif ml == "run out":
            batsman.how_out = "run out"
        else:
            # Fallback: store the raw method (or blank)
            batsman.how_out = m

    def start_new_day(self) -> None:
        # If the match has reached the final day and time has expired, declare a draw.
        # Track the day currently being played (day_counter is the next day number)
        self.current_day = getattr(self, 'day_counter', 1)
        if getattr(self, "day_counter", 1) > getattr(self, "MAX_DAYS", 5):
            self.gui.match_output.insert(tk.END, f"\n--- End of Day {self.MAX_DAYS}: Time expired ---\n")
            self.gui.match_output.insert(tk.END, "\nRESULT: Match Drawn\n")
            self.match_over = True
            self.result_summary = {'type': 'draw'}
            try:
                self.gui.on_match_concluded(self)
            except Exception:
                pass
            try:
                self._showinfo_deferred("Match Finished", "Match Drawn (Time expired)")
            except Exception:
                pass
            return

        # Pick today's condition (weighted)
        template = random.choice(self.MATCH_CONDITIONS_DECK)
        self.current_conditions = template

        self.day_no_play = bool(template.get("no_play", False))
        self.day_overs_lost_start = int(template.get("overs_lost_start", 0) or 0)
        self.day_overs_lost_end = int(template.get("overs_lost_end", 0) or 0)

        # Calculate overs scheduled
        if self.day_no_play:
            self.day_overs_scheduled = 0
        else:
            lost_total = self.day_overs_lost_start + self.day_overs_lost_end
            self.day_overs_scheduled = max(0, self.DAY_OVERS - lost_total)

        # Reset day/session counters
        self.overs_in_day = 0
        self.session_overs_completed = 0
        self.session_number = 1
        self.last_bowler = None

        # Reset bowling limits for the current bowling side for the new day
        bowling_team = self._bowling_team()
        self.bowler_overs_today = {p.name: 0 for p in bowling_team}
        self.bowler_overs_session = {p.name: 0 for p in bowling_team}
        self.last_bowler = None
        self._limits_session_number = self.session_number

        # Retired hurt players may return to bat on a later day.
        # Rule: they should return at the first available opportunity on the *next day of play*.
        # Implementation:
        #  - On day start, move any pending retired-hurt batters (from the CURRENT batting team) into
        #    the returning queue and set a priority flag.
        #  - When selecting the next batter after a wicket, if priority is set, return these players
        #    before selecting unused batters.
        batting_team = self._batting_team()
        moved_any = False
        if getattr(self, 'retired_hurt_pending', None):
            for p in list(self.retired_hurt_pending):
                # Safety: only allow batters from the current innings' batting side to return
                if p not in batting_team:
                    continue
                if p not in self.retired_hurt_returning:
                    self.retired_hurt_returning.append(p)
                    moved_any = True
                # Do NOT overwrite how_out here; keep 'Retired Hurt' visible if innings ends before return.
            # Remove only those that belong to this innings' batting side
            self.retired_hurt_pending[:] = [p for p in self.retired_hurt_pending if p not in batting_team]

        if moved_any:
            self.retired_hurt_priority = True

        # Announce conditions
        msg = f"\n--- Day {self.current_day} Begins ---\nConditions: {template.get('text', '')}\n"
        if self.day_no_play or self.day_overs_scheduled == 0:
            msg += "No play possible today.\n"
        else:
            if self.day_overs_lost_start:
                msg += f"Overs lost at start: {self.day_overs_lost_start}\n"
            if self.day_overs_lost_end:
                msg += f"Overs lost at end: {self.day_overs_lost_end}\n"
            if self.day_overs_scheduled != self.DAY_OVERS:
                msg += f"Overs scheduled today: {self.day_overs_scheduled}/{self.DAY_OVERS}\n"

        self.gui.match_output.insert(tk.END, msg)
        # Refresh bowler selection options immediately for the new day/session
        try:
            self.gui.refresh_bowler_dropdown(bowling_team)
        except Exception:
            pass
        try:
            self.gui.update_live_panel()
        except Exception:
            pass
        self.day_counter += 1

    def _current_condition_modifiers_for_over(self) -> tuple[int, int]:
        # Returns (batsman_modifier, bowler_modifier) for the current over in the day.
        if not self.current_conditions or self.day_no_play:
            return 0, 0

        over_num = self.overs_in_day + 1  # 1-indexed within the day
        phases = self.current_conditions.get("phases", []) or []
        for ph in phases:
            try:
                start = int(ph.get("start", 1))
                end = int(ph.get("end", self.DAY_OVERS))
                if start <= over_num <= end:
                    return int(ph.get("bat", 0) or 0), int(ph.get("bowl", 0) or 0)
            except Exception:
                continue
        return 0, 0
    def _register_bowler_wicket_for_hattrick(self):
        """Track consecutive bowler-attributed wickets on consecutive balls for hat-trick commentary."""
        b = self.bowler
        if self._last_ball_was_bowler_wicket and self._last_wicket_bowler is b:
            self._hattrick_count += 1
        else:
            self._hattrick_count = 1
        self._last_ball_was_bowler_wicket = True
        self._last_wicket_bowler = b

        if self._hattrick_count == 2:
            self.gui.match_output.insert(tk.END, "He's on a hat trick now - can he get the vital third wicket\n")
            self._hattrick_pending_bowler = b
        elif self._hattrick_count == 3:
            self.gui.match_output.insert(tk.END, "A hat trick!!! What an achievement\n")
            self._hattrick_pending_bowler = None
            self._hattrick_count = 0
            self._last_ball_was_bowler_wicket = False
            self._last_wicket_bowler = None

    def _break_hattrick_chain(self):
        """Break the hat-trick chain on any non bowler-wicket delivery."""
        self._last_ball_was_bowler_wicket = False
        self._hattrick_pending_bowler = None
        self._last_wicket_bowler = None

    def _apply_hattrick_miss_prefix(self, line: str) -> str:
        """If a bowler was on a hat-trick (2 consecutive bowler-attributed wickets) and does NOT take the third,
        prefix the *next ball's* commentary with 'Not this time - ' (removing the leading 'Ball N:'),
        then clear the pending state and break the hat-trick chain.
        """
        try:
            pending = getattr(self, "_hattrick_pending_bowler", None)
            current = getattr(self, "bowler", None)
            if pending is not None and current is not None and pending is current:
                # Remove leading 'Ball N:' for the requested style
                line2 = re.sub(r'^Ball\s+\d+:\s*', '', line).rstrip('\n')
                # Clear pending + break chain
                self._hattrick_pending_bowler = None
                self._hattrick_count = 0
                self._last_ball_was_bowler_wicket = False
                self._last_wicket_bowler = None
                return f"Not this time - {line2}\n"
        except Exception:
            pass
        return line

    def _check_batting_milestones(self, batsman):
        """Return milestone text if batsman hits a new milestone in the current innings."""
        runs = getattr(batsman, 'runs', 0)
        if not hasattr(self, '_milestones_awarded') or self._milestones_awarded is None:
            self._milestones_awarded = {}
        awarded = self._milestones_awarded.setdefault(batsman, set())

        milestones = {
            50: "And that's his 50!",
            100: "He lifts his bat to acknowledge a magnificent century!",
            150: "That's 150 - he doesn't look like he's going to stop there",
            200: "A double century - what an achievement",
            300: "He joins the greats like Bradman, Sobers, Sehwag, Sangakkara & Lara with a triple century",
            400: "That's it!!! He's equaled the record for the highest ever Test score",
        }

        for m, text in milestones.items():
            if runs >= m and m not in awarded:
                awarded.add(m)
                return text

        if runs > 400 and 'over400' not in awarded:
            awarded.add('over400')
            return "He's stands alone at the top of the mountain - Test cricket's highest ever innings!"

        return None

    def apply_rating_modifier(self, rating: str, modifier: int) -> str:
        if rating not in self.RATINGS_ORDER:
            return rating
        idx = self.RATINGS_ORDER.index(rating)
        new_idx = max(0, min(len(self.RATINGS_ORDER) - 1, idx + modifier))
        return self.RATINGS_ORDER[new_idx]


    def _take_next_batsman(self, batting_team: List[Player]) -> Optional[Player]:
        """Return the next available batsman for this innings.

        Rules:
        - Unused batters normally come in next.
        - If a player retired hurt on a previous day, they should return at the *first available opportunity*
          on the next day of play. We implement that by giving the returning queue priority when
          self.retired_hurt_priority is True (set at day start if any RH are eligible).
        """
        # Priority return for retired-hurt batters (from next day start)
        if getattr(self, "retired_hurt_returning", None) and self.retired_hurt_returning and getattr(self, "retired_hurt_priority", False):
            p = self.retired_hurt_returning.pop(0)
            # Clear the 'Retired Hurt' marker now that they've resumed their innings
            if getattr(p, "how_out", "").strip().lower() == "retired hurt":
                p.how_out = ""
            # If no more RH batters waiting, drop priority.
            if not self.retired_hurt_returning:
                self.retired_hurt_priority = False
            return p

        # Otherwise use the next unused batter in the XI
        if self.next_batsman_index < len(batting_team):
            p = batting_team[self.next_batsman_index]
            self.next_batsman_index += 1
            return p

        # If no unused batters remain, allow any returning retired-hurt batters (regardless of priority flag)
        if getattr(self, "retired_hurt_returning", None) and self.retired_hurt_returning:
            p = self.retired_hurt_returning.pop(0)
            if getattr(p, "how_out", "").strip().lower() == "retired hurt":
                p.how_out = ""
            if not self.retired_hurt_returning:
                self.retired_hurt_priority = False
            return p

        return None

    def _no_batsmen_left(self, batting_team: List[Player]) -> bool:
        """True if there are no unused batsmen left AND no eligible retired-hurt returnees."""
        return self.next_batsman_index >= len(batting_team) and not (getattr(self, 'retired_hurt_returning', None) or [])

    def _maybe_end_innings_no_batsmen(self, batting_team: List[Player]) -> bool:
        """End the innings if play cannot continue due to lack of batsmen (e.g., retired hurt on final available player)."""
        if len(self.current_batsmen) < 2 and self._no_batsmen_left(batting_team):
            try:
                self.gui.match_output.insert(tk.END, "\n*** Innings complete (no batsmen remaining or eligible) ***\n")
            except Exception:
                pass
            self.end_innings(force=True)
            return True
        return False

    def _batting_team(self) -> List[Player]:
        # Determine batting team based on innings_batting_team mapping (supports follow-on)
        tid = self.innings_batting_team.get(self.innings, 1 if self.innings in (1, 3) else 2)
        return self.team1 if tid == 1 else self.team2

    def _bowling_team(self) -> List[Player]:
        # Bowling team is the opposite of batting team (supports follow-on)
        bt = self.innings_batting_team.get(self.innings, 1 if self.innings in (1, 3) else 2)
        return self.team2 if bt == 1 else self.team1


    def _increment_wicket_and_maybe_end(self):
        """Increment wickets safely; end innings immediately at 10 wickets.
        Returns True if innings ended."""
        # Do not allow wickets beyond 10
        if self.wickets_taken >= 10:
            return True
    
        self.wickets_taken += 1
        self.fow.append((self.wickets_taken, self.runs))
    
        if self.wickets_taken == 10:
            self.end_innings()
            return True
    
        return False

    def start_over(self, bowler_name: str) -> None:
        if self.match_over:
            self._showinfo_deferred("Match Finished", "The match is already finished.")
            return

        # If today has no scheduled overs (washout) or the day has already completed,
        # automatically advance to the next day on the next action.
        if self.day_overs_scheduled == 0 or self.overs_in_day >= self.day_overs_scheduled:
            self.start_new_day()
            return

        batting_team = self._batting_team()
        bowling_team = self._bowling_team()


        # Reset per-session bowling limits at the start of a new session (before selecting a bowler)
        if getattr(self, '_limits_session_number', None) != self.session_number:
            self.bowler_overs_session = {p.name: 0 for p in bowling_team}
            self.last_bowler = None
            self._limits_session_number = self.session_number

        # Select bowler
        self.bowler = next((p for p in bowling_team if p.name == bowler_name), None)
        if not self.bowler:
            messagebox.showerror("Error", "Invalid bowler selected")
            return

        # Ensure tracking dicts include this bowler
        self.bowler_overs_session.setdefault(self.bowler.name, 0)
        self.bowler_overs_today.setdefault(self.bowler.name, 0)

        # Limits
        max_overs_per_bowler_session = 2
        max_overs_per_bowler_day = 4

        if self.bowler_overs_session[self.bowler.name] >= max_overs_per_bowler_session:
            messagebox.showerror("Error", f"{bowler_name} has already bowled {max_overs_per_bowler_session} overs this session.")
            return
        if self.bowler_overs_today[self.bowler.name] >= max_overs_per_bowler_day:
            messagebox.showerror("Error", f"{bowler_name} has already bowled {max_overs_per_bowler_day} overs today.")
            return
        if bowler_name == self.last_bowler:
            messagebox.showerror("Error", "Bowler cannot bowl consecutive overs.")
            return

        self.gui.match_output.insert(tk.END, f"\n--- Over {self.overs_completed + 1}: Bowler {self.bowler.name} ---\n")
        self.current_over_legal_balls = 0

        # Internal: track which session the bowling limits were last reset for
        self._limits_session_number = self.session_number
        if hasattr(self.gui, "update_live_panel"):
            self.gui.update_live_panel()

        ball = 0
        while ball < 6:
            if not self.current_batsmen:
                break

            striker = self.current_batsmen[0]

            bat_mod, bowl_mod = self._current_condition_modifiers_for_over()

            adj_bat_rating = self.apply_rating_modifier(striker.batting_rating, bat_mod)
            base_bowl_rating = self.bowler.bowling_rating if self.bowler.bowling_rating else "A"
            adj_bowl_rating = self.apply_rating_modifier(base_bowl_rating, bowl_mod)

            outcome = self.simulate_ball(striker, self.bowler, adj_bat_rating, adj_bowl_rating)

            # ---------------- HANDLE OUTCOMES ----------------
            # outcome can be:
            # - {"type": "Loose Ball", ...}
            # - {"type": "No Ball", ...}
            # - "W"  (wicket)
            # - int  (runs)
            legal_delivery = True

            bowler_wicket_this_ball = False

            if isinstance(outcome, dict):
                otype = outcome.get("type")

                if otype == "Appeal":
                    appeal_result = str(outcome.get("appeal_result") or "")
                    if appeal_result == "Not Out":
                        _line = f"Ball {ball + 1}: The bowler has appealed. That's Not Out\n"
                        _line = self._apply_hattrick_miss_prefix(_line)
                        self.gui.match_output.insert(tk.END, _line)
                        # Dot ball
                    elif appeal_result == "Out":
                        method = str(outcome.get("method") or "").strip()
                        method_lower = method.lower()

                        # Format dismissal text for specific modes
                        wk_name: Optional[str] = None
                        fielder_name: Optional[str] = None

                        if method_lower == "caught wk":
                            wk_name = self._get_wicketkeeper_name(bowling_team)
                            dismissal_text = f"caught by {wk_name}"
                        elif method_lower == "stumped wk":
                            wk_name = self._get_wicketkeeper_name(bowling_team)
                            dismissal_text = f"stumped by {wk_name}"
                        elif method_lower == "caught":
                            wk_name = self._get_wicketkeeper_name(bowling_team)
                            fielders = [p.name for p in bowling_team if p.name not in {self.bowler.name, wk_name}]
                            fielder_name = random.choice(fielders) if fielders else "a fielder"
                            dismissal_text = f"caught by {fielder_name}"
                        else:
                            dismissal_text = method


                        self.gui.match_output.insert(
                            tk.END,
                            f"Ball {ball + 1}: The bowler has appealed, and {striker.name} is out {dismissal_text}\n",
                        )
                        # Record dismissal on scorecard
                        self._set_dismissal(striker, method, bowling_team, self.bowler, fielder_name=fielder_name, wk_name=wk_name)

                        # Credit the bowler for standard bowler-induced dismissals BEFORE ending the innings (so the 10th wicket counts)
                        if method.lower() in {"bowled", "lbw", "caught", "caught wk", "stumped wk"}:
                            self.bowler.wickets += 1
                            bowler_wicket_this_ball = True
                            self._register_bowler_wicket_for_hattrick()

                        if self._increment_wicket_and_maybe_end():
                            return
                        nb = self._take_next_batsman(batting_team)
                        if nb is not None:
                            self.current_batsmen[0] = nb
                        else:
                            self.current_batsmen = []
                            if self._maybe_end_innings_no_batsmen(batting_team):
                                return
                    elif appeal_result == "No Ball":
                        _line = f"Ball {ball + 1}: The bowler has appealed but it's a NO BALL.\n"
                        _line = self._apply_hattrick_miss_prefix(_line)
                        self.gui.match_output.insert(tk.END, _line)
                        self.runs += 1
                        # 4th innings chase: end immediately mid-over if target passed
                        self.gui.update_score(self.runs, self.wickets_taken, self.extras)
                        if self.check_chase_complete():
                            return
                        self.extras += 1
                        self.extras_nb += 1
                        self.bowler.runs_conceded += 1
                        legal_delivery = False
                    elif appeal_result == "Loose Ball":
                        _line = f"Ball {ball + 1}: The bowler has appealed but it's a loose ball.\n"
                        _line = self._apply_hattrick_miss_prefix(_line)
                        self.gui.match_output.insert(tk.END, _line)
                        card = outcome.get("card") or {}
                        display_text = str(card.get("text", "")).split(",")[0].strip()
                        if display_text:
                            self.gui.match_output.insert(tk.END, f"    {display_text}\n")

                        # Score updates
                        bats_runs = int(card.get("batsman_runs", 0) or 0)
                        extras_runs = int(card.get("extras_runs", 0) or 0)
                        bowler_runs = int(card.get("bowler_runs", 0) or 0)
                        score_inc = int(card.get("score_inc", bats_runs + extras_runs) or 0)

                        striker.runs += bats_runs
                        # milestone checked when logging (inline)
                        milestone = self._check_batting_milestones(striker)
                        if milestone and bats_runs > 0:
                            self.gui.match_output.insert(tk.END, f"    {striker.name} scores {bats_runs} - {milestone}\n")
                        self.runs += score_inc
                        # 4th innings chase: end immediately mid-over if target passed
                        self.gui.update_score(self.runs, self.wickets_taken, self.extras)
                        if self.check_chase_complete():
                            return
                        self.bowler.runs_conceded += bowler_runs

                        # Track extras breakdown (best-effort)
                        self.extras += extras_runs
                        text_lower = str(card.get("text", "")).lower()
                        if "no ball" in text_lower or card.get("no_ball", False):
                            self.extras_nb += 1
                        if "bye" in text_lower:
                            self.extras_b += extras_runs
                        if "leg bye" in text_lower or "leg byes" in text_lower:
                            self.extras_lb += extras_runs

                        # Ball counting: if extra_ball True, this is NOT a legal delivery
                        if card.get("extra_ball", False) or card.get("no_ball", False):
                            legal_delivery = False
                        out_flag = ""

                        # Retired hurt: replace striker, no wicket
                        if card.get("retired_hurt", False):
                            self.gui.match_output.insert(tk.END, f"{striker.name} RETIRED HURT\n")
                            # Record on batting card as Retired Hurt (may change to not out next day)
                            striker.how_out = "Retired Hurt"
                            if striker not in self.retired_hurt_pending:
                                self.retired_hurt_pending.append(striker)

                            nb = self._take_next_batsman(batting_team)
                            if nb is not None:
                                self.current_batsmen[0] = nb
                            else:
                                self.current_batsmen = []
                                if self._maybe_end_innings_no_batsmen(batting_team):
                                    return
                        else:
                            out_flag = (card.get("out") or "")
                        if isinstance(out_flag, str) and out_flag.strip().lower() in {"striker", "non-striker"}:
                            # Some loose-ball run outs happen at the bowler's end (often the non-striker).
                            method_tmp = str(card.get("method") or "").strip().lower()
                            txt_tmp = str(card.get("text", "")).lower()
                            who = out_flag.strip().lower()
                            if method_tmp == "run out" and "bowler" in txt_tmp:
                                who = "non-striker"

                            out_player = self.current_batsmen[0] if who == "striker" else self.current_batsmen[1]
                            replace_index = 0 if who == "striker" else 1

                            method = str(card.get("method") or "").strip()
                            method_lower = method.lower()

                            # Credit bowler only for bowler-attributed dismissals BEFORE ending the innings (so the 10th wicket counts)
                            if method_lower in {"bowled", "lbw", "caught", "caught wk", "stumped wk"}:
                                self.bowler.wickets += 1
                                bowler_wicket_this_ball = True
                                self._register_bowler_wicket_for_hattrick()

                            # Determine fielder / wicketkeeper names where relevant
                            wk_name = None
                            fielder_name = None
                            card_text_lower = str(card.get("text", "")).lower()

                            if method_lower == "caught":
                                if "wicketkeeper" in card_text_lower or "keeper" in card_text_lower or "wk" in card_text_lower:
                                    wk_name = self._get_wicketkeeper_name(bowling_team)
                                    fielder_name = wk_name
                                else:
                                    candidates = [p.name for p in bowling_team if p.name not in {self.bowler.name, self._get_wicketkeeper_name(bowling_team)}]
                                    fielder_name = random.choice(candidates) if candidates else "a fielder"
                            elif method_lower in {"caught wk", "stumped wk"}:
                                wk_name = self._get_wicketkeeper_name(bowling_team)
                                fielder_name = wk_name

                            # Record dismissal on scorecard
                            self._set_dismissal(out_player, method, bowling_team, self.bowler, fielder_name=fielder_name, wk_name=wk_name)

                            self.gui.match_output.insert(tk.END, f"WICKET! ({out_player.name} out by {method})\n")
                            if self._increment_wicket_and_maybe_end():
                                return

                            nb = self._take_next_batsman(batting_team)
                            if nb is not None:
                                self.current_batsmen[replace_index] = nb
                            else:
                                # No replacement available; innings will end when <2 batsmen remain
                                self.current_batsmen = [p for p in self.current_batsmen if p is not out_player]
                                if self._maybe_end_innings_no_batsmen(batting_team):
                                    return


                elif otype == "No Ball":
                    # 1 run no-ball, extra delivery
                    _line = f"Ball {ball + 1}: NO BALL\n"
                    _line = self._apply_hattrick_miss_prefix(_line)
                    self.gui.match_output.insert(tk.END, _line)
                    self.runs += 1
                    # 4th innings chase: end immediately mid-over if target passed
                    self.gui.update_score(self.runs, self.wickets_taken, self.extras)
                    if self.check_chase_complete():
                        return
                    self.extras += 1
                    self.extras_nb += 1
                    self.bowler.runs_conceded += 1
                    legal_delivery = False

                else:
                    # Unknown dict outcome (usually a loose-ball style payload missing a type):
                    # Interpret it as a loose ball so we don't accidentally create "dot" balls.
                    display_text = str(outcome.get("text", "")).split(",")[0].strip()
                    if display_text:
                        _line = f"Ball {ball + 1}: {display_text}\n"
                        _line = self._apply_hattrick_miss_prefix(_line)
                        self.gui.match_output.insert(tk.END, _line)
                    else:
                        # Fallback text
                        _line = f"Ball {ball + 1}: loose ball\n"
                        _line = self._apply_hattrick_miss_prefix(_line)
                        self.gui.match_output.insert(tk.END, _line)

                    bats_runs = int(outcome.get("batsman_runs", 0) or 0)
                    extras_runs = int(outcome.get("extras_runs", 0) or 0)
                    bowler_runs = int(outcome.get("bowler_runs", 0) or 0)
                    score_inc = int(outcome.get("score_inc", bats_runs + extras_runs) or 0)

                    striker.runs += bats_runs
                    # milestone checked when logging (inline)
                    milestone = self._check_batting_milestones(striker)
                    if milestone and bats_runs > 0:
                        self.gui.match_output.insert(tk.END, f"    {striker.name} scores {bats_runs} - {milestone}\n")
                    self.runs += score_inc
                    self.extras += extras_runs
                    self.bowler.runs_conceded += bowler_runs

                    # Extras breakdown (best-effort)
                    text_lower = str(outcome.get("text", "")).lower()
                    if "no ball" in text_lower or outcome.get("no_ball", False):
                        self.extras_nb += 1
                        legal_delivery = False
                    if "bye" in text_lower:
                        self.extras_b += extras_runs
                    if "leg bye" in text_lower or "leg byes" in text_lower:
                        self.extras_lb += extras_runs

                    # Retired hurt
                    out_flag = ""
                    if outcome.get("retired_hurt", False):
                        self.gui.match_output.insert(tk.END, f"{striker.name} RETIRED HURT\n")
                        striker.how_out = "Retired Hurt"
                        if striker not in self.retired_hurt_pending:
                            self.retired_hurt_pending.append(striker)
                        nb = self._take_next_batsman(batting_team)
                        if nb is not None:
                            self.current_batsmen[0] = nb
                        else:
                            self.current_batsmen = []
                            if self._maybe_end_innings_no_batsmen(batting_team):
                                return
                    else:
                        out_flag = (outcome.get("out") or "")

                    if isinstance(out_flag, str) and out_flag.strip().lower() == "striker":
                        method = str(outcome.get("method") or "").strip()
                        method_lower = method.lower()

                        if method_lower in {"bowled", "lbw", "caught", "caught wk", "stumped wk"}:
                            self.bowler.wickets += 1
                            bowler_wicket_this_ball = True
                            self._register_bowler_wicket_for_hattrick()

                        if self._increment_wicket_and_maybe_end():
                            return
                        wk_name = None
                        fielder_name = None
                        if method_lower == "caught":
                            if "wicketkeeper" in text_lower or "keeper" in text_lower or "wk" in text_lower:
                                wk_name = self._get_wicketkeeper_name(bowling_team)
                                fielder_name = wk_name
                            else:
                                candidates = [p.name for p in bowling_team if p.name not in {self.bowler.name, self._get_wicketkeeper_name(bowling_team)}]
                                fielder_name = random.choice(candidates) if candidates else "a fielder"
                        elif method_lower in {"caught wk", "stumped wk"}:
                            wk_name = self._get_wicketkeeper_name(bowling_team)
                            fielder_name = wk_name

                        self._set_dismissal(striker, method, bowling_team, self.bowler, fielder_name=fielder_name, wk_name=wk_name)
                        self.gui.match_output.insert(tk.END, f"WICKET! ({striker.name} out by {method})\n")

                        nb = self._take_next_batsman(batting_team)
                        if nb is not None:
                            self.current_batsmen[0] = nb
                        else:
                            self.current_batsmen = self.current_batsmen[1:] if len(self.current_batsmen) > 1 else []
                            if self._maybe_end_innings_no_batsmen(batting_team):
                                return

                    # Update scoreboard / chase check
                    self.gui.update_score(self.runs, self.wickets_taken, self.extras)
                    if self.check_chase_complete():
                        return


            elif outcome == "W":
                # Generic wicket outcome (treated as Bowled for scorecard purposes)
                self.bowler.wickets += 1
                bowler_wicket_this_ball = True
                self._register_bowler_wicket_for_hattrick()

                try:
                    self._set_dismissal(striker, "Bowled", bowling_team, self.bowler)
                except Exception:
                    pass
                self.gui.match_output.insert(tk.END, f"Ball {ball + 1}: WICKET! ({striker.name} out bowled)\n")

                if self._increment_wicket_and_maybe_end():
                    return
                nb = self._take_next_batsman(batting_team)
                if nb is not None:
                    self.current_batsmen[0] = nb
                else:
                                self.current_batsmen = []
                                if self._maybe_end_innings_no_batsmen(batting_team):
                                    return

            else:
                runs = int(outcome)
                self.runs += runs
                striker.runs += runs
                # milestone checked when logging (inline)
                if runs == 4:
                    striker.fours += 1
                elif runs == 6:
                    striker.sixes += 1
                self.bowler.runs_conceded += runs
                line = f"Ball {ball + 1}: {striker.name} scores {runs}"
                milestone = self._check_batting_milestones(striker)
                if milestone:
                    line += f" - {milestone}"
                self.gui.match_output.insert(tk.END, self._apply_hattrick_miss_prefix(line + "\n"))

                # Update scoreboard / chase check (4th innings)
                try:
                    self.gui.update_score(self.runs, self.wickets_taken, self.extras)
                except Exception:
                    pass
                if self.check_chase_complete():
                    return

                # Rotate strike on odd runs
                if runs % 2 == 1 and len(self.current_batsmen) == 2:
                    self.current_batsmen[0], self.current_batsmen[1] = self.current_batsmen[1], self.current_batsmen[0]

            # Break hat-trick chain on any non bowler-wicket delivery
            if not bowler_wicket_this_ball:
                self._break_hattrick_chain()

            # Update balls faced only on legal deliveries (including byes/leg byes/run-outs etc)
            if legal_delivery:
                striker.balls_faced += 1
                ball += 1
                self.current_over_legal_balls = ball
                if hasattr(self.gui, "update_live_panel"):
                    self.gui.update_live_panel()
            else:
                # Extra delivery: do not increment ball count
                if hasattr(self.gui, "update_live_panel"):
                    self.gui.update_live_panel()
                pass

            # End innings if all out
            if self.wickets_taken >= 10 or len(self.current_batsmen) < 2:
                break

        # End-of-over strike rotation (only if two batsmen still in)
        if len(self.current_batsmen) == 2:
            self.current_batsmen[0], self.current_batsmen[1] = self.current_batsmen[1], self.current_batsmen[0]

        # Update bowler stats (over completed if we reached/attempted 6 legal balls or innings ended mid-over)
        self.bowler.overs_bowled += 1
        self.bowler_overs_session[self.bowler.name] += 1
        self.bowler_overs_today[self.bowler.name] += 1

        self.overs_completed += 1
        self.overs_in_day += 1
        # Track overs within the current session
        self.session_overs_completed += 1
        self.last_bowler = bowler_name
        # Automatically end the session after a fixed number of overs
        # IMPORTANT: per-session bowling limits must reset immediately at the session break (before the next bowler is selected)
        if self.session_overs_completed >= self.overs_per_session and (self.day_overs_scheduled == 0 or self.overs_in_day < self.day_overs_scheduled):
            self.session_number += 1
            self.session_overs_completed = 0
            self.last_bowler = None  # allow any bowler after the break
            # Reset per-session limits for *all* bowlers in the bowling team
            self.bowler_overs_session = {p.name: 0 for p in bowling_team}
            self._limits_session_number = self.session_number
            self.gui.match_output.insert(tk.END, f"\n--- Session break: starting session {self.session_number} ---\n")

        # Update GUI
        self.gui.update_score(self.runs, self.wickets_taken, self.extras)
        if self.check_chase_complete():
            return
        self.gui.update_batting_chart(batting_team)
        self.gui.update_bowling_chart(bowling_team)
        self.gui.refresh_bowler_dropdown(bowling_team)
        if hasattr(self.gui, 'update_live_panel'):
            self.gui.update_live_panel()

        # End innings if all out
        if self.wickets_taken >= 10:
            self.end_innings()
        # End of day (stumps)
        if not self.match_over and self.day_overs_scheduled > 0 and self.overs_in_day >= self.day_overs_scheduled:
            self.gui.match_output.insert(tk.END, f"\n--- Stumps: Day complete ({self.day_overs_scheduled} overs) ---\n")
            self.start_new_day()


    def _snapshot_innings_summary(self) -> None:
        # Capture a snapshot of the current innings for scorecards / tabs.
        batting_team = self._batting_team()
        bowling_team = self._bowling_team()

        batting_rows = []
        for p in batting_team:
            batting_rows.append({
                "name": p.name,
                "runs": p.runs,
                "balls": p.balls_faced,
                "fours": p.fours,
                "sixes": p.sixes,
                "how_out": p.how_out or ("not out" if (p.balls_faced > 0 or p.runs > 0) else ""),
            })

        bowling_rows = []
        for p in bowling_team:
            if not str(getattr(p, "bowling_rating", "") or "").strip():
                continue
            bowling_rows.append({
                "name": p.name,
                "overs": getattr(p, "overs_bowled", 0),
                "runs": getattr(p, "runs_conceded", 0),
                "wkts": getattr(p, "wickets", 0),
            })

        self.innings_summaries[self.innings] = {
            "innings": self.innings,
            "batting_team_name": self.gui.get_batting_team_name() if hasattr(self.gui, "get_batting_team_name") else "",
            "runs": self.runs,
            "wickets": self.wickets_taken,
            "overs": self.overs_completed,
            "extras": self.extras,
            "extras_b": self.extras_b,
            "extras_lb": self.extras_lb,
            "extras_nb": self.extras_nb,
            "extras_w": getattr(self, "extras_w", 0),
            "fow": list(self.fow),
            "batting_rows": batting_rows,
            "bowling_rows": bowling_rows,
        }

    def declare_innings(self) -> None:
        self.innings_declared = True
        # Batting side declares the innings closed immediately.
        batting_name = self.gui.get_batting_team_name() if hasattr(self.gui, "get_batting_team_name") else "Batting team"
        self.gui.match_output.insert(tk.END, f"\n*** {batting_name} have declared their innings at {self.runs}/{self.wickets_taken} ***\n")
        self.end_innings()

    def end_innings(self, force: bool = False) -> None:
        # Legitimate innings end conditions ONLY
        if (not force) and (not getattr(self, 'innings_declared', False)) and self.wickets_taken < 10:
            return
        # Save snapshot for tabs
        try:
            self._snapshot_innings_summary()
        except Exception:
            pass
        if hasattr(self.gui, "render_innings_scorecards"):
            try:
                self.gui.render_innings_scorecards(self.innings, self.innings_summaries.get(self.innings, {}))
            except Exception:
                pass


        # If follow-on enforced: match can finish after innings 3 via an innings victory
        if self.innings == 3 and getattr(self, "follow_on_enforced", False) and self.innings_batting_team.get(3, 2) == 2:
            try:
                t1 = int(self.innings_summaries.get(1, {}).get("runs", 0))
                t2 = int(self.innings_summaries.get(2, {}).get("runs", 0)) + int(self.innings_summaries.get(3, {}).get("runs", 0))
            except Exception:
                t1, t2 = 0, 0
            if t2 < t1:
                margin = t1 - t2
                team1 = getattr(self.gui, "loaded_team1_name", None) or "Team 1"
                self.gui.match_output.insert(tk.END, f"\nRESULT: {team1} win by an innings and {margin} runs\n")
                self.result_summary = {"type": "win", "winner": 1, "margin": f"an innings and {margin} runs"}
                self.match_over = True
                try:
                    self.gui.on_match_concluded(self)
                except Exception:
                    pass
                self.gui.match_output.insert(tk.END, "\nMatch over.\n")
                return


        if self.innings >= 4:
            self.determine_result()
            self.match_over = True
            try:
                self.gui.on_match_concluded(self)
            except Exception:
                pass
            self.gui.match_output.insert(tk.END, "\nMatch over.\n")
            return

        self.gui.match_output.insert(
            tk.END,
            f"\n*** Innings {self.innings} complete ***\n"
        )

        # Offer follow-on if available (after innings 2 completes)
        self.offer_follow_on_if_available()

        # Advance to next innings
        self.innings += 1
        # Set batting team for the new innings (supports follow-on)
        if self.innings == 2:
            self.innings_batting_team[2] = 2
        elif self.innings == 3:
            self.innings_batting_team[3] = 2 if self.follow_on_enforced else 1
        elif self.innings == 4:
            self.innings_batting_team[4] = 1 if self.innings_batting_team.get(3, 1) == 2 else 2

        # Reset innings counters
        self.runs = 0
        self.wickets_taken = 0
        self.overs_completed = 0
        self.current_over_legal_balls = 0

        # Internal: track which session the bowling limits were last reset for
        self._limits_session_number = self.session_number
        self.fow = []

        # Reset innings extras
        self.extras = 0
        self.extras_nb = 0
        self.extras_b = 0
        self.extras_lb = 0
        self.extras_w = 0

        batting_team = self._batting_team()
        bowling_team = self._bowling_team()

        # New innings (incl. follow-on): reset bowling allocations
        self.bowler_overs_session = {p.name: 0 for p in bowling_team}
        self.bowler_overs_today = {p.name: 0 for p in bowling_team}
        self.last_bowler = None
        self._limits_session_number = self.session_number

        # Reset per-innings player stats
        for p in batting_team:
            if hasattr(p, 'reset_innings_batting_stats'):
                p.reset_innings_batting_stats()
            else:
                p.runs = 0
                p.balls_faced = 0
                p.fours = 0
                p.sixes = 0
                p.how_out = ""
        for p in bowling_team:
            if hasattr(p, 'reset_innings_bowling_stats'):
                p.reset_innings_bowling_stats()
            else:
                p.wickets = 0
                p.overs_bowled = 0
                p.runs_conceded = 0

        # Opening batsmen for new innings
        self.current_batsmen = [batting_team[0], batting_team[1]]
        self.next_batsman_index = 2

        self.bowler = None
        self.last_bowler = None

        self.gui.match_output.insert(tk.END, f"\n--- Innings {self.innings} begins ---\nSelect a bowler for the new innings and continue.\n")
        self.gui.refresh_bowler_dropdown(bowling_team)

        if hasattr(self.gui, "select_innings_tab"):
            try:
                self.gui.select_innings_tab(self.innings)
            except Exception:
                pass
        if hasattr(self.gui, "update_live_panel"):
            self.gui.update_live_panel()


    def _team_totals_completed(self) -> tuple[int, int]:
        # Returns (team1_total_completed, team2_total_completed) from completed innings only.
        t1 = self.innings_summaries.get(1, {}).get("runs", 0) + self.innings_summaries.get(3, {}).get("runs", 0)
        t2 = self.innings_summaries.get(2, {}).get("runs", 0) + self.innings_summaries.get(4, {}).get("runs", 0)
        return t1, t2

    def _batting_team_is_team1(self) -> bool:
        # Innings order: 1=T1 bats, 2=T2 bats, 3=T1 bats, 4=T2 bats
        return self.innings in (1, 3)

    def _current_cumulative_totals(self) -> tuple[int, int]:
        # Returns (team1_total_so_far, team2_total_so_far) including current innings runs.
        t1_completed, t2_completed = self._team_totals_completed()
        if self._batting_team_is_team1():
            t1_completed += self.runs
        else:
            t2_completed += self.runs
        return t1_completed, t2_completed


    def totals_by_team_completed(self) -> tuple[int, int]:
        t1 = 0
        t2 = 0
        for inn, summ in self.innings_summaries.items():
            runs = int(summ.get("runs", 0) or 0)
            tid = self.innings_batting_team.get(int(inn), 1 if int(inn) in (1, 3) else 2)
            if tid == 1:
                t1 += runs
            else:
                t2 += runs
        return t1, t2

    def totals_by_team_including_current(self) -> tuple[int, int]:
        t1, t2 = self.totals_by_team_completed()
        bt = self.innings_batting_team.get(self.innings, 1 if self.innings in (1, 3) else 2)
        if bt == 1:
            t1 += int(self.runs or 0)
        else:
            t2 += int(self.runs or 0)
        return t1, t2

    def offer_follow_on_if_available(self) -> None:
        if self.innings != 2:
            return
        t1_inn1 = int(self.innings_summaries.get(1, {}).get("runs", 0) or 0)
        t2_inn1 = int(self.innings_summaries.get(2, {}).get("runs", 0) or 0)
        lead = t1_inn1 - t2_inn1
        if lead >= self.follow_on_threshold:
            team1 = self.gui.get_display_team_name_for_match_side(1)
            try:
                self.follow_on_enforced = bool(messagebox.askyesno(
                    "Follow-on Available",
                    f"{team1} lead by {lead} runs. Enforce the follow-on?"
                ))
            except Exception:
                self.follow_on_enforced = False

    def check_chase_complete(self) -> bool:
        # Mid-over chase completion in 4th innings
        if self.innings != 4 or getattr(self, "match_over", False):
            return False

        t1, t2 = self.totals_by_team_including_current()
        team1 = self.gui.get_display_team_name_for_match_side(1)
        team2 = self.gui.get_display_team_name_for_match_side(2)
        bt = self.innings_batting_team.get(4, 2)

        if bt == 1 and t1 > t2:
            wkts_remaining = max(0, 10 - self.wickets_taken)
            self.gui.match_output.insert(tk.END, f"\nRESULT: {team1} win by {wkts_remaining} wickets\n")
            self.match_over = True
            self.result_summary = {'type': 'win', 'winner': 1, 'margin': f'{wkts_remaining} wickets'}
            try:
                self.gui.on_match_concluded(self)
            except Exception:
                pass
            try:
                self._showinfo_deferred("Match Finished", f"{team1} win by {wkts_remaining} wickets")
            except Exception:
                pass
            return True

        if bt == 2 and t2 > t1:
            wkts_remaining = max(0, 10 - self.wickets_taken)
            self.gui.match_output.insert(tk.END, f"\nRESULT: {team2} win by {wkts_remaining} wickets\n")
            self.match_over = True
            self.result_summary = {'type': 'win', 'winner': 2, 'margin': f'{wkts_remaining} wickets'}
            try:
                self.gui.on_match_concluded(self)
            except Exception:
                pass
            try:
                self._showinfo_deferred("Match Finished", f"{team2} win by {wkts_remaining} wickets")
            except Exception:
                pass
            return True

        return False
    def determine_result(self) -> None:
        if getattr(self, "match_over", False):
            return
        if len(self.innings_summaries) < 4:
            return

        t1, t2 = self.totals_by_team_completed()
        team1 = self.gui.get_display_team_name_for_match_side(1)
        team2 = self.gui.get_display_team_name_for_match_side(2)

        if t1 > t2:
            self.gui.match_output.insert(tk.END, f"\nRESULT: {team1} win by {t1 - t2} runs\n")
            self.result_summary = {'type': 'win', 'winner': 1, 'margin': f'{t1 - t2} runs'}
        elif t2 > t1:
            self.gui.match_output.insert(tk.END, f"\nRESULT: {team2} win by {t2 - t1} runs\n")
            self.result_summary = {'type': 'win', 'winner': 2, 'margin': f'{t2 - t1} runs'}
        else:
            self.gui.match_output.insert(tk.END, "\nRESULT: Match Tied\n")
            self.result_summary = {'type': 'tie'}

        self.match_over = True
        try:
            self.gui.on_match_concluded(self)
        except Exception:
            pass
    def simulate_ball(self, batsman: Player, bowler: Player, adj_bat_rating: str, adj_bowl_rating: str):
        # Get the batting row (fallback row if rating missing)
        bat_row = self.BATTING_CHART.get(adj_bat_rating, ["", ""] + ["*"] * 11)

        # Roll 2d6
        dice = random.randint(1, 6) + random.randint(1, 6)

        # Handle Loose Ball automatically on 12
        if dice == 12:
            card = random.choice(self.LOOSE_BALL_CARDS)
            return self._loose_ball_payload(card)

        bat_result = bat_row[dice] if dice < len(bat_row) else bat_row[-1]

        # Wicket / appeal check on batting chart
        # Appeals ONLY occur when the batting chart result is "*"
        if bat_result == "*":
            bowl_row = self.BOWLER_WICKET_CHART.get(adj_bowl_rating, ["", ""] + ["Not out"] * 11)
            dice_w = random.randint(1, 6) + random.randint(1, 6)
            bowl_result = bowl_row[dice_w] if dice_w < len(bowl_row) else "Not out"

            if bowl_result == "No ball":
                return {"type": "Appeal", "appeal_result": "No Ball"}

            if bowl_result == "Loose Ball":
                card = random.choice(self.LOOSE_BALL_CARDS)
                return {"type": "Appeal", "appeal_result": "Loose Ball", "card": self._loose_ball_payload(card)}

            if bowl_result in {"Caught", "Bowled", "LBW", "Stumped WK", "Caught WK"}:
                return {"type": "Appeal", "appeal_result": "Out", "method": bowl_result}

            # Not out
            return {"type": "Appeal", "appeal_result": "Not Out"}

        if bat_result == "Loose Ball":
            card = random.choice(self.LOOSE_BALL_CARDS)
            return self._loose_ball_payload(card)

        # Runs
        try:
            return int(bat_result)
        except Exception:
            return 0

    def _loose_ball_payload(self, card: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize payload to what start_over expects.
        return {
            "type": "Loose Ball",
            "text": card.get("text", ""),
            "out": card.get("out"),
            "method": card.get("method"),
            "batsman_runs": int(card.get("batsman_runs", 0) or 0),
            "bowler_runs": int(card.get("bowler_runs", 0) or 0),
            "extras_runs": int(card.get("extras_runs", 0) or 0),
            "score_inc": int(card.get("score_inc", 0) or 0),
            "no_ball": bool(card.get("no_ball", False)),
            "extra_ball": bool(card.get("extra_ball", False)),
            "retired_hurt": bool(card.get("retired_hurt", False)),
        }


# -------------------- GUI CLASS --------------------

    def _reset_bowler_limits_for_new_innings(self, bowling_team):
        """New innings => all bowlers are available again (reset per-session and per-day allocations)."""
        self.last_bowler = None



    def _check_followon_result_after_innings3(self):
        """If follow-on is enforced, the match can finish after innings 3 (innings victory)."""
        if not getattr(self, "follow_on_enforced", False):
            return False
        if self.current_innings != 3:
            return False
        inn = getattr(self, "innings_summaries", {})
        inn1, inn2, inn3 = inn.get(1, {}), inn.get(2, {}), inn.get(3, {})
        if not inn1 or not inn2 or not inn3:
            return False
        if inn2.get("team") != inn3.get("team"):
            return False
        lead_team = inn1.get("team")
        follow_team = inn2.get("team")
        total_follow = int(inn2.get("runs", 0)) + int(inn3.get("runs", 0))
        total_lead = int(inn1.get("runs", 0))
        if total_follow <= total_lead:
            margin = total_lead - total_follow
            self.match_over = True
            self.result_summary = f"{lead_team} won by an innings and {margin} runs"
            return True
        return False


    def _bowler_can_bowl(self, bowler) -> bool:
        if bowler is None:
            return False
        max_overs_per_bowler_session = 2
        max_overs_per_bowler_day = 4
        name = bowler.name
        if self.bowler_overs_session.get(name, 0) >= max_overs_per_bowler_session:
            return False
        if self.bowler_overs_today.get(name, 0) >= max_overs_per_bowler_day:
            return False
        if self.last_bowler == name:
            return False
        return True


class CricketGUI:
    all_players_cache: Optional[List[Player]] = None  # class-level cache

    def _showinfo_deferred(self, title, message):
        """Show messagebox.showinfo, but defer if ball-by-ball playback is running."""
        try:
            if getattr(self, "_ball_by_ball_playing", False) or getattr(self, "_suppress_live_updates", False):
                self._pending_end_dialog = (title, message)
                return
            from tkinter import messagebox
            self._showinfo_deferred(title, message)
        except Exception:
            pass

    def _prompt_save_scorecard_deferred(self):
        """Prompt to save scorecard, but defer if ball-by-ball playback is running."""
        try:
            if getattr(self, "_ball_by_ball_playing", False) or getattr(self, "_suppress_live_updates", False):
                self._pending_save_scorecard = True
                return
            self.prompt_save_scorecard()
        except Exception:
            pass

    def _flush_end_of_match_ui(self):
        """Run any deferred end-of-match dialogs/prompts after ball-by-ball playback finishes."""
        try:
            # Ensure UI reflects final state first
            try:
                self.update_live_panel()
            except Exception:
                pass
            try:
                self.update_batting_chart()
                self.update_bowling_chart()
            except Exception:
                pass

            if self._pending_end_dialog:
                title, msg = self._pending_end_dialog
                self._pending_end_dialog = None
                self._showinfo_deferred(title, msg)

            if self._pending_save_scorecard:
                self._pending_save_scorecard = False
                self._prompt_save_scorecard_deferred()
        except Exception:
            pass


    def _find_background_path(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            for fname in ("background.png", "background.jpg", "background.jpeg"):
                cand = os.path.join(base_dir, fname)
                if os.path.exists(cand):
                    return cand
        except Exception:
            pass
        return None

    def _blend_to_white(self, img, opacity=0.18):
        """Return a watermark-like version blended heavily toward white.
        opacity: 0..1 where lower is more transparent."""
        try:
            img = img.convert("RGBA")
            white = Image.new("RGBA", img.size, (255, 255, 255, 255))
            # Blend factor towards original image
            return Image.blend(white, img, opacity)
        except Exception:
            return img

    def _ensure_top_bg_canvas(self):
        """Create a background label that covers the whole top section of the match screen."""
        if Image is None or ImageTk is None:
            return
        if getattr(self, "_top_bg_label", None) is not None:
            return

        self._top_bg_path = self._find_background_path()
        if not self._top_bg_path:
            return

        # A Label works better than a Canvas here because Canvas.lower/tkraise are tag-based.
        self._top_bg_label = tk.Label(self.match_screen, borderwidth=0, highlightthickness=0)
        # Cover rows 0-3 (overview + controls). Match log starts below this.
        self._top_bg_label.grid(row=0, column=0, rowspan=4, columnspan=3, sticky="nsew")
        self._top_bg_label.lower()

        self._top_bg_tk = None

        def _redraw(_evt=None):
            try:
                w = max(1, int(self._top_bg_label.winfo_width()))
                h = max(1, int(self._top_bg_label.winfo_height()))
                if w <= 1 or h <= 1:
                    return
                img = Image.open(self._top_bg_path)
                img = img.resize((w, h))
                img = self._blend_to_white(img, opacity=0.16)  # more transparent watermark
                self._top_bg_tk = ImageTk.PhotoImage(img)
                self._top_bg_label.configure(image=self._top_bg_tk)
                self._top_bg_label.lower()
            except Exception:
                pass

        self._top_bg_label.bind("<Configure>", _redraw)
        self.match_screen.after(50, _redraw)

    def _raise_top_widgets(self):

        """Ensure match widgets stay above the background canvas."""
        try:
            for w in (getattr(self, "live_canvas", None),
                      getattr(self, "controls_frame", None)):
                if w is not None:
                    w.tkraise()
            # also raise match_button_frame if present
            if getattr(self, "match_button_frame", None) is not None:
                self.match_button_frame.tkraise()
        except Exception:
            pass



    def _setup_background(self) -> None:
        """Optional faded background image behind the entire UI."""
        # Create a full-window canvas and keep it behind other widgets.
        self._bg_canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self._bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self._bg_canvas.lower()
        except Exception:
            pass

        # If Pillow isn't available, do nothing further.
        if Image is None or ImageTk is None:
            self._bg_img = None
            self._bg_original = None
            return

        # Look for the background image next to the script file.
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base_dir = os.getcwd()
        img_path = os.path.join(base_dir, "cricket-2511043_1920.jpg")
        if not os.path.exists(img_path):
            self._bg_img = None
            self._bg_original = None
            return

        try:
            self._bg_original = Image.open(img_path).convert("RGB")
        except Exception:
            self._bg_img = None
            self._bg_original = None
            return

        # Redraw whenever the window size changes.
        self.root.bind("<Configure>", self._on_bg_resize)

        # Initial draw (after geometry has applied)
        self.root.after(50, self._redraw_background)

    def _on_bg_resize(self, event: tk.Event) -> None:
        # Debounce resize events a bit
        if getattr(self, "_bg_resize_job", None):
            try:
                self.root.after_cancel(self._bg_resize_job)
            except Exception:
                pass
        self._bg_resize_job = self.root.after(100, self._redraw_background)


    def _on_root_configure(self, event=None) -> None:
        """Handle root resize/configure events.

        Currently used to trigger background redraw (debounced) and keep any future
        root-level layout adjustments in one place.
        """
        try:
            # Delegate to background resize handler if it exists
            if hasattr(self, "_on_bg_resize"):
                self._on_bg_resize(event)
        except Exception:
            pass
    def _redraw_background(self) -> None:
        if Image is None or ImageTk is None:
            return
        if getattr(self, "_bg_original", None) is None:
            return

        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())

        try:
            img = self._bg_original.resize((w, h), Image.LANCZOS)
            # Fade towards white: keep ~10% of the image.
            base = Image.new("RGB", (w, h), (255, 255, 255))
            faded = Image.blend(base, img, 0.10)
            self._bg_img = ImageTk.PhotoImage(faded)

            self._bg_canvas.delete("all")
            self._bg_canvas.create_image(0, 0, image=self._bg_img, anchor="nw")
            self._bg_canvas.lower()
        except Exception:
            # Never let background issues crash the app.
            return

    def __init__(self, root: tk.Tk):
        self.root = root
        self._settings = self._load_settings()
        root.title("Dice Cricket Simulator")
        root.geometry("1400x950")
        root.state("zoomed")
        self._build_menubar()
        # Use a modern ttk theme
        try:
            style = ttk.Style()
            style.theme_use("clam")
            # Prefer white panel backgrounds
            try:
                self.root.configure(bg="white")
            except Exception:
                pass
            try:
                style.configure("TFrame", background="white")
                style.configure("TLabelframe", background="white")
                style.configure("TLabelframe.Label", background="white")
                style.configure("TLabel", background="white")
                style.configure("TNotebook", background="white")
                style.configure("TNotebook.Tab", background="white")
            except Exception:
                pass
        except Exception:
            pass
        # --- Option 1 theme: white app with olive accents ---
        control_colour = "#9DAE11"
        neutral_button = "#F2F2F2"
        border_colour = "#DADADA"

        # Neutral default for controls; olive only for primary actions and selected tab
        style.configure("TFrame", background="white")
        style.configure("TLabel", background="white", foreground="#1A1A1A")
        style.configure("TLabelframe", background="white", bordercolor=border_colour, relief="solid")
        style.configure("TLabelframe.Label", background="white", foreground="#1A1A1A", font=("TkDefaultFont", 10, "bold"))

        # Default buttons = neutral
        style.configure("TButton", background=neutral_button, foreground="#1A1A1A", padding=6)
        style.map("TButton", background=[("active", neutral_button)])

        # Combobox = neutral (white)
        style.configure("TCombobox", fieldbackground="white", background="white", foreground="#1A1A1A")

        # Notebook tabs: size indicates active innings, not colour
        style.configure(
            "TNotebook",
            background="white",
            borderwidth=0
        )

        # Base (inactive) tabs
        style.configure(
            "TNotebook.Tab",
            background="white",
            foreground="#1A1A1A",
            padding=(8, 4),
            font=("TkDefaultFont", 9)
        )

        # Active tab = larger + bold
        style.map(
            "TNotebook.Tab",
            font=[
                ("selected", ("TkDefaultFont", 11, "bold")),
                ("!selected", ("TkDefaultFont", 9))
            ]
        )

        self._setup_background()
        root.bind("<Configure>", self._on_root_configure)

        # Validation colours (instance attrs so other methods can use them)
        self.VALID_OK = "#006400"     # dark green
        self.VALID_BAD = "#8B0000"    # dark red
        self.VALID_NEUTRAL = "black"

        # -------------------- SCREEN FRAMES --------------------
        # The app has two screens in the same window:
        #   1) Team Selection (setup_screen)
        #   2) Match Screen (match_screen)
        # Only one is visible at a time.
        self.setup_screen = ttk.Frame(root)
        self.match_screen = ttk.Frame(root)

        self.setup_screen.grid(row=0, column=0, sticky="nsew")
        self.match_screen.grid(row=0, column=0, sticky="nsew")

        # Root expands the current screen
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # Configure setup screen grid
        self.setup_screen.grid_columnconfigure(0, weight=1)
        self.setup_screen.grid_columnconfigure(1, weight=0)
        self.setup_screen.grid_columnconfigure(2, weight=1)
        self.setup_screen.grid_rowconfigure(2, weight=1)

        # Configure match screen grid (mirrors the previous root grid layout)
        self.match_screen.grid_columnconfigure(0, weight=1)
        self.match_screen.grid_columnconfigure(1, weight=0)
        self.match_screen.grid_columnconfigure(2, weight=1)
        self.match_screen.grid_rowconfigure(4, weight=1)
        self.match_screen.grid_rowconfigure(5, weight=1)

        # Start on the team selection screen
        self.show_setup_screen()

        # Load players
        self.all_players = self.load_players()
        if not self.all_players:
            messagebox.showerror("Error", "No players loaded (check all_test_players.csv).")
            root.destroy()
            return

        self.countries = sorted({c.strip() for p in self.all_players for c in str(p.country).split('/') if c.strip()})

        # -------------------- TEAM FRAMES --------------------
        self.team1_vars, self.team1_checkbuttons, self.visible_t1, self.team1_frame = self.create_team_frame("Team 1", 0)
        self.team2_vars, self.team2_checkbuttons, self.visible_t2, self.team2_frame = self.create_team_frame("Team 2", 2)
        # -------------------- SAVED TEAM SELECTION BOXES --------------------
        # (Load Team controls are placed inside each team panel below the player lists)

        self.saved_teams = self.load_saved_teams()
        # Series state
        self.series_active = False
        self.series_total = 1
        self.series_index = 0
        self.series_score = {'team1': 0, 'team2': 0, 'draw': 0, 'tie': 0}
        self.series_team1 = None
        self.series_team2 = None
        self._handling_match_conclusion = False
        self._series_transitioning = False

        # Team 1 saved listbox
        # -------------------- LOAD TEAMS + LIVE SELECTION SUMMARY --------------------
        # Team 1 panel (summary on left, load listbox on right)
        self.team1_panel = ttk.Frame(self.setup_screen)
        self.team1_panel.grid(row=2, column=0, padx=5, pady=2, sticky="nw")

        self.team1_sel_bat_var = tk.StringVar(value="0 Batsmen Selected")
        self.team1_sel_bowl_var = tk.StringVar(value="0 Bowlers Selected")
        self.team1_sel_wk_var = tk.StringVar(value="0 Wicketkeepers Selected")

        self.team1_summary = ttk.Frame(self.team1_panel)
        self.team1_summary.grid(row=0, column=0, sticky="nw")
        ttk.Label(self.team1_summary, textvariable=self.team1_sel_bat_var, anchor="w").pack(anchor="w")
        self.team1_sel_bowl_lbl = tk.Label(self.team1_summary, textvariable=self.team1_sel_bowl_var, fg=self.VALID_BAD)
        self.team1_sel_bowl_lbl.pack(anchor="w")
        self.team1_sel_wk_lbl = tk.Label(self.team1_summary, textvariable=self.team1_sel_wk_var, fg=self.VALID_BAD)
        self.team1_sel_wk_lbl.pack(anchor="w")

        self.team1_load = ttk.Frame(self.team1_panel)
        self.team1_load.grid(row=1, column=0, sticky="nw")

        ttk.Label(self.team1_load, text="Load Team 1").pack(anchor="w")
        self.team1_listbox = tk.Listbox(self.team1_load, height=5)
        self.team1_listbox.pack(anchor="w")

        # Team 2 panel (summary on left, load listbox on right)
        self.team2_panel = ttk.Frame(self.setup_screen)
        self.team2_panel.grid(row=2, column=2, padx=5, pady=2, sticky="ne")

        self.team2_sel_bat_var = tk.StringVar(value="0 Batsmen Selected")
        self.team2_sel_bowl_var = tk.StringVar(value="0 Bowlers Selected")
        self.team2_sel_wk_var = tk.StringVar(value="0 Wicketkeepers Selected")

        self.team2_summary = ttk.Frame(self.team2_panel)
        self.team2_summary.grid(row=0, column=0, sticky="nw")
        ttk.Label(self.team2_summary, textvariable=self.team2_sel_bat_var, anchor="w").pack(anchor="w")
        self.team2_sel_bowl_lbl = tk.Label(self.team2_summary, textvariable=self.team2_sel_bowl_var, fg=self.VALID_BAD)
        self.team2_sel_bowl_lbl.pack(anchor="w")
        self.team2_sel_wk_lbl = tk.Label(self.team2_summary, textvariable=self.team2_sel_wk_var, fg=self.VALID_BAD)
        self.team2_sel_wk_lbl.pack(anchor="w")

        self.team2_load = ttk.Frame(self.team2_panel)
        self.team2_load.grid(row=1, column=0, sticky="nw")

        ttk.Label(self.team2_load, text="Load Team 2").pack(anchor="w")
        self.team2_listbox = tk.Listbox(self.team2_load, height=5)
        self.team2_listbox.pack(anchor="w")

        self._refresh_saved_team_listboxes()
        self.update_selection_summary()

        self.load_team1_button = ttk.Button(self.team1_load, text="Load Selected Team 1", command=lambda: self.load_saved_team(1))
        self.load_team1_button.pack(anchor="w", pady=(4, 0))
        self.load_team2_button = ttk.Button(self.team2_load, text="Load Selected Team 2", command=lambda: self.load_saved_team(2))
        self.load_team2_button.pack(anchor="w", pady=(4, 0))

        # -------------------- SETUP CONTROLS (SERIES / START / BATTING ORDER) --------------------
        # These controls belong on the Team Selection screen (setup_screen).
        self.setup_controls_frame = ttk.Frame(self.setup_screen)
        self.setup_controls_frame.grid(row=2, column=1, padx=8, pady=2, sticky="n")
        self.setup_controls_frame.grid_columnconfigure(0, weight=1)

        # Center the setup controls under the team selection panels
        self.setup_controls_inner = ttk.Frame(self.setup_controls_frame)
        self.setup_controls_inner.pack(anchor="n")

        # -------------------- SERIES MODE --------------------
        self.series_var = tk.StringVar(value="Single Test")

        ttk.Label(self.setup_controls_inner, text="Series:").pack(side="left", padx=(0, 4))
        self.series_menu = ttk.Combobox(self.setup_controls_inner,
            textvariable=self.series_var,
            state="readonly",
            values=["Single Test", "3 Tests", "5 Tests"],
            width=10,
        )
        self.series_menu.pack(side="left", padx=(0, 12))

        self.start_button = ttk.Button(self.setup_controls_inner, text="Start Match", command=self.start_match)
        self.start_button.pack(side="left", padx=5)

        self.edit_t1_order_button = ttk.Button(self.setup_controls_inner, text="Edit Team 1 Order", command=lambda: self.open_batting_order_editor(1)
        )
        self.edit_t1_order_button.pack(side="left", padx=5)

        self.edit_t2_order_button = ttk.Button(self.setup_controls_inner, text="Edit Team 2 Order", command=lambda: self.open_batting_order_editor(2)
        )
        self.edit_t2_order_button.pack(side="left", padx=5)

        # Tooltips
        attach_tooltip(self.start_button, "Start the match (or the next Test in the selected series).")
        attach_tooltip(self.edit_t1_order_button, "Set the batting order for Team 1.")
        attach_tooltip(self.edit_t2_order_button, "Set the batting order for Team 2.")

        # Manual batting order overrides (set via "Edit Batting Order")
        self.manual_team1_order: Optional[List[str]] = None
        self.manual_team2_order: Optional[List[str]] = None
        self._manual_order_sel_snapshot_t1: Optional[set] = None
        self._manual_order_sel_snapshot_t2: Optional[set] = None

        # -------------------- MATCH CONTROLS (BOWLER + BALL-BY-BALL) --------------------
        self.controls_frame = ttk.Frame(self.match_screen)
        self.controls_frame.grid(row=3, column=0, columnspan=3, pady=(2, 0), padx=5, sticky="ew")
        self.controls_frame.grid_columnconfigure(0, weight=0)
        self.controls_frame.grid_columnconfigure(1, weight=0)
        self.controls_frame.grid_columnconfigure(2, weight=1)
        self.controls_frame.grid_columnconfigure(3, weight=0)
        self.controls_frame.grid_columnconfigure(4, weight=0)

        ttk.Label(self.controls_frame, text="Select Bowler for Over").grid(row=0, column=0, columnspan=2, sticky="w")

        self.bowler_var = tk.StringVar()
        self.bowler_menu = ttk.Combobox(self.controls_frame, textvariable=self.bowler_var, state="readonly", width=28)
        self.bowler_menu.grid(row=1, column=0, columnspan=2, sticky="w", padx=(0, 8))

        # Over actions (moved under bowler selector)
        self.sim_over_button = ttk.Button(self.controls_frame, text="Simulate Over", command=self.simulate_over)
        self.sim_over_button.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.declare_button = ttk.Button(self.controls_frame, text="Declare Innings", command=self.declare_innings, state="disabled")
        self.declare_button.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

        # Tooltips
        attach_tooltip(self.sim_over_button, "Simulate the next over using the selected bowler.")
        attach_tooltip(self.declare_button, "Declare the innings (available when enabled).")

        # Ball-by-ball commentary display + controls
        # Make the display taller so it can comfortably use a larger font.
        self.ball_by_ball_text_var = tk.StringVar(value="")
        try:
            # NOTE: ttk expects a real Font object; ("TkDefaultFont", 18) is treated as a *family name*
            # and often won’t change anything on Windows themes. Use a copy of the named font instead.
            self._ball_by_ball_font = tkfont.nametofont("TkDefaultFont").copy()
            self._ball_by_ball_font.configure(size=18)
            ttk.Style().configure("BallByBall.TEntry", font=self._ball_by_ball_font)
            # Wicket-highlight style (red text)
            ttk.Style().configure("BallByBallWicket.TEntry", font=self._ball_by_ball_font, foreground="red")
        except Exception:
            self._ball_by_ball_font = None
        self.ball_by_ball_entry = ttk.Entry(
            self.controls_frame,
            textvariable=self.ball_by_ball_text_var,
            width=70,
            state="readonly",
            style="BallByBall.TEntry",
        )
        # Force font directly on the widget as well (Windows themes sometimes ignore ttk style fonts for Entry).
        if self._ball_by_ball_font is not None:
            try:
                self.ball_by_ball_entry.configure(font=self._ball_by_ball_font)
            except Exception:
                pass

        # ipady increases the widget height so the larger font isn't clipped
        self.ball_by_ball_entry.grid(row=1, column=2, sticky="ew", padx=(0, 8), ipady=10)

        self.ball_by_ball_enabled = tk.BooleanVar(value=True)
        self.ball_by_ball_toggle_btn = ttk.Button(self.controls_frame, text="ON", width=6, command=self.toggle_ball_by_ball)
        self.ball_by_ball_toggle_btn.grid(row=1, column=3, sticky="e", padx=(0, 6))

        attach_tooltip(self.ball_by_ball_toggle_btn, "Toggle ball-by-ball commentary on/off.")

        ttk.Label(self.controls_frame, text="Speed").grid(row=0, column=4, sticky="e")
        self.ball_by_ball_speed_var = tk.StringVar(value="Slow")
        self.ball_by_ball_speed_menu = ttk.Combobox(
            self.controls_frame,
            textvariable=self.ball_by_ball_speed_var,
            state="readonly",
            values=["Slow", "Medium", "Fast"],
            width=8
        )
        self.ball_by_ball_speed_menu.grid(row=1, column=4, sticky="e")

        attach_tooltip(self.ball_by_ball_speed_menu, "Choose the ball-by-ball speed (Slow/Medium/Fast).")

        # Playback guard for ball-by-ball mode
        self._ball_by_ball_playing = False
        self._flush_end_of_match_ui()
# -------------------- MATCH BUTTONS --------------------
        # Match-only controls (keep Exit Match on the match screen).
        self.match_button_frame = ttk.Frame(self.controls_frame)
        self.match_button_frame.grid(row=2, column=2, columnspan=3, padx=(8, 0), pady=(4, 0), sticky="e")

        self.exit_button = ttk.Button(self.match_button_frame, text="Exit Match", command=self.exit_match, state="disabled")
        self.exit_button.pack(side="left", padx=5)
        attach_tooltip(self.exit_button, "Exit the current match.")

# -------------------- OUTPUT TEXT BOXES --------------------
        # Match progress (with scrollbars, no line wrapping)
        self.match_frame = ttk.Frame(self.match_screen)
        self.match_frame.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.match_frame.grid_columnconfigure(0, weight=1)
        self.match_frame.grid_rowconfigure(0, weight=1)

        self.match_output = tk.Text(self.match_frame, width=120, height=15, wrap="none")
        self.match_output.grid(row=0, column=0, sticky="nsew")
        self.match_ys = tk.Scrollbar(self.match_frame, orient="vertical", command=self.match_output.yview)
        self.match_ys.grid(row=0, column=1, sticky="ns")
        self.match_xs = tk.Scrollbar(self.match_frame, orient="horizontal", command=self.match_output.xview)
        self.match_xs.grid(row=1, column=0, sticky="ew")
        self.match_output.configure(yscrollcommand=self.match_ys.set, xscrollcommand=self.match_xs.set)        

        # -------------------- LIVE INNINGS SUMMARY (CENTRE PANEL) --------------------
        # NOTE: We render the top "match overview" area on a Canvas so the match background image
        # can appear behind the text (ttk widgets are not transparent on Windows).
        self._ensure_top_bg_canvas()
        self.live_canvas = tk.Canvas(self.match_screen, highlightthickness=0, bd=0)
        self.live_canvas.grid(row=0, column=1, padx=5, pady=(28, 5), sticky="nsew")

        # Keep this row from collapsing and allow the canvas to expand nicely when the window resizes.
        try:
            self.match_screen.grid_rowconfigure(0, weight=0)
            self.match_screen.grid_rowconfigure(0, minsize=195)
            self.match_screen.grid_columnconfigure(1, weight=1)
        except Exception:
            pass

        # Canvas item ids (created once, then updated via itemconfig)
        self._live_items = {}

        # Background state
        self._live_bg_src = None          # PIL.Image (original)
        self._live_bg_tk = None           # ImageTk.PhotoImage (resized)
        self._live_bg_item = None         # canvas image item id

        def _ensure_live_canvas_items():
            # Create text items once
            if self._live_items:
                return

            # Title
            self._live_items["title"] = self.live_canvas.create_text(
                0, 0, text="", anchor="n", font=("TkDefaultFont", 14, "bold")
            )

            # Left (batsmen)
            self._live_items["bat_hdr"] = self.live_canvas.create_text(
                0, 0, text="", anchor="nw", font=("Consolas", 12, "bold")
            )
            self._live_items["bat1"] = self.live_canvas.create_text(
                0, 0, text="", anchor="nw", font=("Consolas", 12)
            )
            self._live_items["bat2"] = self.live_canvas.create_text(
                0, 0, text="", anchor="nw", font=("Consolas", 12)
            )

            # Right (match situation + FOW)
            self._live_items["sit_hdr"] = self.live_canvas.create_text(
                0, 0, text="MATCH SITUATION", anchor="nw", font=("TkDefaultFont", 10, "bold")
            )
            self._live_items["sit"] = self.live_canvas.create_text(
                0, 0, text="", anchor="nw", font=("TkDefaultFont", 12)
            )
            self._live_items["time"] = self.live_canvas.create_text(
                0, 0, text="", anchor="nw", font=("TkDefaultFont", 11)
            )
            self._live_items["fow_hdr"] = self.live_canvas.create_text(
                0, 0, text="FALL OF WICKETS", anchor="nw", font=("TkDefaultFont", 10, "bold")
            )
            self._live_items["fow"] = self.live_canvas.create_text(
                0, 0, text="", anchor="nw", font=("TkDefaultFont", 11)
            )

            # Give everything a consistent readable fill
            for k, item in self._live_items.items():
                try:
                    self.live_canvas.itemconfig(item, fill="black")
                except Exception:
                    pass

        def _load_live_background_once():
            # Disabled: no background inside Match Overview panel.
            self._live_bg_src = None
            return

        def _render_live_canvas():
            # Called on resize (and when switching to match screen) to keep background + layout correct.
            _ensure_live_canvas_items()
            _load_live_background_once()

            w = max(1, int(self.live_canvas.winfo_width() or 1))
            h = max(1, int(self.live_canvas.winfo_height() or 1))

            # --- Background image disabled for Match Overview panel ---
            if self._live_bg_item is not None:
                try:
                    self.live_canvas.delete(self._live_bg_item)
                except Exception:
                    pass
                self._live_bg_item = None

            # --- Layout (two columns) ---
            pad_x = 14
            pad_y = 10
            col_gap = 22
            title_h = 28

            col_w = max(1, (w - (pad_x * 2) - col_gap) // 2)
            left_x = pad_x
            right_x = pad_x + col_w + col_gap

            # Title centered across both columns
            self.live_canvas.coords(self._live_items["title"], w // 2, pad_y)

            # Left batsmen table
            y0 = pad_y + title_h
            self.live_canvas.coords(self._live_items["bat_hdr"], left_x, y0)
            self.live_canvas.coords(self._live_items["bat1"], left_x, y0 + 22)
            self.live_canvas.coords(self._live_items["bat2"], left_x, y0 + 44)

            # Right situation / time / FOW
            ry = y0
            self.live_canvas.coords(self._live_items["sit_hdr"], right_x, ry)
            self.live_canvas.coords(self._live_items["sit"], right_x, ry + 20)
            self.live_canvas.coords(self._live_items["time"], right_x, ry + 44)
            self.live_canvas.coords(self._live_items["fow_hdr"], right_x, ry + 74)
            self.live_canvas.coords(self._live_items["fow"], right_x, ry + 94)

            # Constrain wrapping width so long strings (time) stay on one line when possible.
            try:
                self.live_canvas.itemconfig(self._live_items["sit"], width=col_w)
                self.live_canvas.itemconfig(self._live_items["time"], width=col_w)
                self.live_canvas.itemconfig(self._live_items["fow"], width=col_w)
            except Exception:
                pass

        # Fixed height that matches the intended "top overview" feel without stretching the UI.
        # (This makes the match screen stable across themes/DPIs.)
        try:
            self.live_canvas.configure(height=190)
        except Exception:
            pass

        self._render_live_canvas = _render_live_canvas  # store bound function for later use
        self.live_canvas.bind("<Configure>", lambda e: self._render_live_canvas())

        # Initial render once Tk has sizes
        try:
            self.root.after_idle(self._render_live_canvas)
        except Exception:
            pass


        # Bottom scorecards area (separate layout grid so top widgets don't force the same widths)
        self.scorecards_frame = ttk.Frame(self.match_screen)
        self.scorecards_frame.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.scorecards_frame.grid_rowconfigure(0, weight=1)
        self.scorecards_frame.grid_columnconfigure(0, weight=3)  # Batting (wider)
        self.scorecards_frame.grid_columnconfigure(1, weight=1)  # Spacer
        self.scorecards_frame.grid_columnconfigure(2, weight=2)  # Bowling

        # Batting card (tabbed by innings)
        self.batting_frame = ttk.Frame(self.scorecards_frame)
        self.batting_frame.grid(row=0, column=0, sticky="nsew")
        self.batting_frame.grid_columnconfigure(0, weight=1)
        self.batting_frame.grid_rowconfigure(0, weight=1)

        self.batting_notebook = ttk.Notebook(self.batting_frame)
        self.batting_notebook.grid(row=0, column=0, sticky="nsew")

        self.batting_charts: Dict[int, tk.Text] = {}
        for inn in (1, 2, 3, 4):
            tab = ttk.Frame(self.batting_notebook)
            self.batting_notebook.add(tab, text=f"Innings {inn}")
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            # Wider batting card to accommodate long names + "How out" text + totals/extras
            txt = tk.Text(tab, width=120, height=15, wrap="none")
            txt.grid(row=0, column=0, sticky="nsew")
            xs = tk.Scrollbar(tab, orient="horizontal", command=txt.xview)
            xs.grid(row=1, column=0, sticky="ew")
            ys = tk.Scrollbar(tab, orient="vertical", command=txt.yview)
            ys.grid(row=0, column=1, sticky="ns")
            txt.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
            self.batting_charts[inn] = txt

        # Spacer column between batting and bowling cards (keeps the visual gap you want)
        self.scorecards_spacer = ttk.Frame(self.scorecards_frame)
        self.scorecards_spacer.grid(row=0, column=1, sticky="nsew")

        # Bowling figures (tabbed by innings)
        self.bowling_frame = ttk.Frame(self.scorecards_frame)
        self.bowling_frame.grid(row=0, column=2, sticky="nsew")
        self.bowling_frame.grid_columnconfigure(0, weight=1)
        self.bowling_frame.grid_rowconfigure(0, weight=1)

        self.bowling_notebook = ttk.Notebook(self.bowling_frame)
        self.bowling_notebook.grid(row=0, column=0, sticky="nsew")

        self.bowling_charts: Dict[int, tk.Text] = {}
        for inn in (1, 2, 3, 4):
            tab = ttk.Frame(self.bowling_notebook)
            self.bowling_notebook.add(tab, text=f"Innings {inn}")
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            txt = tk.Text(tab, width=80, height=15, wrap="none")
            txt.grid(row=0, column=0, sticky="nsew")
            xs = tk.Scrollbar(tab, orient="horizontal", command=txt.xview)
            xs.grid(row=1, column=0, sticky="ew")
            ys = tk.Scrollbar(tab, orient="vertical", command=txt.yview)
            ys.grid(row=0, column=1, sticky="ns")
            txt.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
            self.bowling_charts[inn] = txt

        # Auto-fit window width to be ~20px wider than the match progress window,
        # but never exceed the screen width.
        try:
            root.update_idletasks()
            sw = int(root.winfo_screenwidth())
            sh = int(root.winfo_screenheight())
            target_w = int(root.winfo_reqwidth()) + 20
            target_w = min(target_w, max(900, sw - 60))
            target_h = min(950, max(700, sh - 80))
            root.geometry(f"{target_w}x{target_h}")
        except Exception:
            pass

        # Track loaded saved teams
        self.loaded_team1_name: Optional[str] = None
        self.loaded_team2_name: Optional[str] = None

        # Show startup 'How To Play' overlay (can be disabled)
        try:
            self.root.after_idle(self._maybe_show_startup_howto)
        except Exception:
            pass


    # -------------------- MENU / HELP --------------------

    # ---- Settings persistence (for startup overlay etc.) ----
    def show_setup_screen(self) -> None:
        """Show the Team Selection (setup) screen and hide the Match screen."""
        try:
            self.match_screen.grid_remove()
        except Exception:
            pass
        try:
            self.setup_screen.grid()
        except Exception:
            pass

    def show_match_screen(self) -> None:
        """Show the Match screen and hide the Team Selection (setup) screen."""
        try:
            self.setup_screen.grid_remove()
        except Exception:
            pass
        try:
            self.match_screen.grid()
        except Exception:
            pass


    def _settings_path(self) -> str:
        # Prefer per-user AppData on Windows, otherwise home directory.
        try:
            if os.name == "nt":
                base = os.environ.get("APPDATA") or os.path.expanduser("~")
            else:
                base = os.path.expanduser("~")
        except Exception:
            base = os.getcwd()
        return os.path.join(base, "max_walker_sim_settings.json")

    def _load_settings(self) -> dict:
        defaults = {"show_startup_howto": True}
        p = self._settings_path()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
        return defaults

    def _save_settings(self) -> None:
        p = self._settings_path()
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except Exception:
            # Never crash the app due to settings write issues.
            pass

    # ---- Startup How To Play overlay ----
    def _maybe_show_startup_howto(self) -> None:
        try:
            if not getattr(self, "_settings", {}).get("show_startup_howto", True):
                return
        except Exception:
            return
        self.show_startup_howto()

    def show_startup_howto(self) -> None:
        """Modal-ish How To Play overlay."""
        try:
            win = tk.Toplevel(self.root)
        except Exception:
            return

        win.title("How To Play")
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass

        frame = ttk.Frame(win, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        title = ttk.Label(frame, text="How To Play", font=("TkDefaultFont", 14, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        txt = tk.Text(frame, wrap="word", height=18)
        txt.grid(row=1, column=0, sticky="nsew")
        ys = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        ys.grid(row=1, column=1, sticky="ns")
        txt.configure(yscrollcommand=ys.set)

        txt.insert("1.0", STARTUP_HOWTO_TEXT)
        txt.configure(state="disabled")

        disable_var = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(frame, text="Don't show this again", variable=disable_var)
        chk.grid(row=2, column=0, sticky="w", pady=(10, 0))

        btns = ttk.Frame(frame)
        btns.grid(row=3, column=0, sticky="e", pady=(10, 0))

        def _close():
            try:
                if disable_var.get():
                    self._settings["show_startup_howto"] = False
                    self._save_settings()
            except Exception:
                pass
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        ttk.Button(btns, text="Close", command=_close).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Open Help", command=lambda: (self.show_help(), _close())).grid(row=0, column=1)

        # Center on the root window and keep on-screen
        try:
            win.update_idletasks()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            ww = win.winfo_reqwidth()
            wh = win.winfo_reqheight()
            x = rx + max(0, (rw - ww) // 2)
            y = ry + max(0, (rh - wh) // 2)
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = max(10, min(x, sw - ww - 10))
            y = max(10, min(y, sh - wh - 10))
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass

        win.protocol("WM_DELETE_WINDOW", _close)

    def reset_startup_howto(self) -> None:
        try:
            self._settings["show_startup_howto"] = True
            self._save_settings()
            self._showinfo_deferred("How To Play", "The startup How To Play popup has been re-enabled.")
        except Exception:
            pass

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="How To Play", command=self.show_startup_howto)
        help_menu.add_command(label="Help", command=self.show_help)
        help_menu.add_separator()
        help_menu.add_command(label="Re-enable Startup How To Play", command=self.reset_startup_howto)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    def show_help(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Help")
        win.geometry("900x650")
        try:
            win.transient(self.root)
        except Exception:
            pass

        container = ttk.Frame(win, padding=10)
        container.pack(fill="both", expand=True)

        title = ttk.Label(container, text="Help", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", pady=(0, 8))

        text_frame = ttk.Frame(container)
        text_frame.pack(fill="both", expand=True)

        yscroll = ttk.Scrollbar(text_frame, orient="vertical")
        yscroll.pack(side="right", fill="y")

        txt = tk.Text(text_frame, wrap="word", yscrollcommand=yscroll.set)
        txt.pack(side="left", fill="both", expand=True)
        yscroll.config(command=txt.yview)

        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")

        btns = ttk.Frame(container)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")

    def show_about(self) -> None:
        self._showinfo_deferred(
            "About",
            "Max Walker Cricket Simulator\n\n"
            "Help is available from the Help menu.\n"
            "This application is built with Tkinter.\n"
            "Written by Tony Francis."
        )


    # -------------------- LOAD PLAYERS --------------------
    @classmethod
    def load_players(cls) -> List[Player]:
        # Return cached list if already loaded
        if cls.all_players_cache is not None:
            return cls.all_players_cache

        players: List[Player] = []
        csv_path = "all_test_players.csv"
        if not os.path.exists(csv_path):
            messagebox.showerror("Error", f"{csv_path} not found")
            cls.all_players_cache = []
            return cls.all_players_cache

        try:
            with open(csv_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    players.append(
                        Player(
                            name=row["Name"],
                            country=row["Country"],
                            bat=row["BattingRating"],
                            bowl=row["BowlingRating"] if row.get("BowlingRating") else None,
                            wk=str(row.get("WK", "")).strip().lower() in {"yes","y","true","1","wk"},
                        )
                    )
        except UnicodeDecodeError:
            # Fallback for non-UTF8 CSVs on Windows
            with open(csv_path, encoding="cp1252", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    players.append(
                        Player(
                            name=row["Name"],
                            country=row["Country"],
                            bat=row["BattingRating"],
                            bowl=row["BowlingRating"] if row.get("BowlingRating") else None,
                            wk=str(row.get("WK", "")).strip().lower() in {"yes","y","true","1","wk"},
                        )
                    )
        except KeyError as e:
            messagebox.showerror("CSV Error", f"Missing column in {csv_path}: {e}")
            cls.all_players_cache = []
            return cls.all_players_cache
        except Exception as e:
            messagebox.showerror("CSV Error", f"Failed reading {csv_path}: {e}")
            cls.all_players_cache = []
            return cls.all_players_cache

        cls.all_players_cache = players
        return cls.all_players_cache

    # -------------------- CREATE TEAM FRAME --------------------
    def create_team_frame(self, title: str, col: int):
        frame = ttk.Frame(self.setup_screen)
        frame.grid(row=0, column=col, padx=5, pady=5, sticky="nsew")

        ttk.Label(frame, text=title).pack()

        canvas = tk.Canvas(frame, width=350, height=290)
        scroll = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        vars_list: List[tk.BooleanVar] = []
        checkbuttons: List[tk.Checkbutton] = []
        visible_players: List[Player] = []
        for p in self.all_players:
            # Only include players with a batting OR bowling rating
            bat_ok = bool(str(getattr(p, 'batting_rating', '') or '').strip())
            bowl_ok = bool(str(getattr(p, 'bowling_rating', '') or '').strip())
            if not bat_ok and not bowl_ok:
                continue

            visible_players.append(p)
            var = tk.BooleanVar()
            cb = tk.Checkbutton(inner, text=p.display(), variable=var, anchor="w", justify="left", fg=("darkblue" if p.is_wk else "black"), command=self.update_selection_summary)
            cb.pack(anchor="w", fill="x")
            vars_list.append(var)
            checkbuttons.append(cb)

        country_var = tk.StringVar(value="All")
        country_cb = ttk.Combobox(frame, textvariable=country_var, state="readonly", values=["All"] + self.countries)
        country_cb.pack(pady=(4, 0))
        country_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter(visible_players, checkbuttons, country_var.get()))

        ttk.Button(frame, text=f"Save {title}", command=lambda t=title: self.save_team(visible_players, vars_list, 1 if '1' in t else 2)).pack(pady=(4, 0))

        # Clear all selections in this team list
        ttk.Button(frame, text="Clear Selection", command=lambda: ([v.set(False) for v in vars_list], self.update_selection_summary())).pack(pady=(4, 0))

        return vars_list, checkbuttons, visible_players, frame

    # -------------------- APPLY FILTER --------------------
    def apply_filter(self, players: List[Player], checkbuttons: List[tk.Checkbutton], country: str) -> None:
        # Hide non-matching players (instead of greying them out) and support dual-country entries like "AUS/ENG".
        selected = (country or "All").strip()
        for p, cb in zip(players, checkbuttons):
            # Always remove from layout first; we will re-pack only if it matches.
            try:
                cb.pack_forget()
            except Exception:
                pass

            player_countries = {c.strip() for c in str(p.country).split('/') if c.strip()}
            match = (selected == "All") or (selected in player_countries)

            if match:
                cb.config(state="normal", fg=("darkblue" if getattr(p, "is_wk", False) else "black"))
                cb.pack(anchor="w", fill="x")
            else:
                cb.config(state="disabled")


    
    # -------------------- UPDATE TEAM SELECTION SUMMARY --------------------

    def update_selection_summary(self):
        """Update the live 'x selected' lines and validation colours for both teams."""

        def count_for(players, vars_list):
            bat = bowl = wk = 0
            for p, v in zip(players, vars_list):
                if not v.get():
                    continue
                if str(getattr(p, "batting_rating", "") or "").strip():
                    bat += 1
                if str(getattr(p, "bowling_rating", "") or "").strip():
                    bowl += 1
                if getattr(p, "is_wk", False):
                    wk += 1
            return bat, bowl, wk

        # Default totals
        b1 = bo1 = wk1 = 0
        b2 = bo2 = wk2 = 0

        if hasattr(self, "visible_t1") and hasattr(self, "team1_vars"):
            b1, bo1, wk1 = count_for(self.visible_t1, self.team1_vars)

        if hasattr(self, "visible_t2") and hasattr(self, "team2_vars"):
            b2, bo2, wk2 = count_for(self.visible_t2, self.team2_vars)

        # --- Team 1 ---
        if hasattr(self, "team1_sel_bat_var"):
            self.team1_sel_bat_var.set(f"{b1} Batsmen Selected")
        if hasattr(self, "team1_sel_bowl_var"):
            self.team1_sel_bowl_var.set(f"{bo1} Bowlers Selected")
        if hasattr(self, "team1_sel_bowl_lbl"):
            self.team1_sel_bowl_lbl.config(fg=self.VALID_OK if bo1 >= 5 else self.VALID_BAD)

        if hasattr(self, "team1_sel_wk_var"):
            self.team1_sel_wk_var.set(f"{wk1} Wicketkeepers Selected")
        if hasattr(self, "team1_sel_wk_lbl"):
            self.team1_sel_wk_lbl.config(fg=self.VALID_OK if wk1 >= 1 else self.VALID_BAD)

        # --- Team 2 ---
        if hasattr(self, "team2_sel_bat_var"):
            self.team2_sel_bat_var.set(f"{b2} Batsmen Selected")
        if hasattr(self, "team2_sel_bowl_var"):
            self.team2_sel_bowl_var.set(f"{bo2} Bowlers Selected")
        if hasattr(self, "team2_sel_bowl_lbl"):
            self.team2_sel_bowl_lbl.config(fg=self.VALID_OK if bo2 >= 5 else self.VALID_BAD)

        if hasattr(self, "team2_sel_wk_var"):
            self.team2_sel_wk_var.set(f"{wk2} Wicketkeepers Selected")
        if hasattr(self, "team2_sel_wk_lbl"):
            self.team2_sel_wk_lbl.config(fg=self.VALID_OK if wk2 >= 1 else self.VALID_BAD)


    # -------------------- LOAD SAVED TEAMS --------------------

        # If selection changed after setting a manual batting order, drop the manual order
        self._clear_manual_order_if_selection_changed()

    def load_saved_teams(self) -> Dict[str, List[str]]:
        teams: Dict[str, List[str]] = {}
        if os.path.exists("saved_teams.csv"):
            try:
                with open("saved_teams.csv", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) < 2:
                            continue
                        teams[row[0]] = row[1:]
            except Exception:
                # If file encoding differs
                with open("saved_teams.csv", encoding="cp1252", newline="") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) < 2:
                            continue
                        teams[row[0]] = row[1:]
        return teams

    def _refresh_saved_team_listboxes(self) -> None:
        self.team1_listbox.delete(0, tk.END)
        self.team2_listbox.delete(0, tk.END)
        for team_name in self.saved_teams:
            self.team1_listbox.insert(tk.END, team_name)
            self.team2_listbox.insert(tk.END, team_name)

    
    # -------------------- HIDE TEAM LOAD CONTROLS --------------------
    def hide_team_load_controls(self) -> None:
        # These are only needed before the match starts.
        for w in [
            getattr(self, "load_team1_label", None),
            getattr(self, "load_team2_label", None),
            getattr(self, "team1_panel", None),
            getattr(self, "team2_panel", None),
            getattr(self, "team1_listbox", None),
            getattr(self, "team2_listbox", None),
            getattr(self, "load_team1_button", None),
            getattr(self, "load_team2_button", None),
        ]:
            if w is None:
                continue
            try:
                w.grid_remove()
            except Exception:
                try:
                    w.pack_forget()
                except Exception:
                    pass

# -------------------- SAVE TEAM --------------------
    def save_team(self, players: List[Player], vars_list: List[tk.BooleanVar], team_no: int = 0) -> None:
        selected_indices = [i for i, v in enumerate(vars_list) if v.get()]
        if len(selected_indices) != 11:
            messagebox.showerror("Error", f"You have selected {len(selected_indices)} players. Please select 11.")
            return

        team_name = simpledialog.askstring("Save Team", "Team Name:")
        if not team_name:
            return

        # If saving from the current selection UI, use this saved name immediately
        # for the currently-selected team (so series/match UI uses it right away).
        if team_no == 1:
            self.loaded_team1_name = team_name
        elif team_no == 2:
            self.loaded_team2_name = team_name

        row = [team_name] + [players[i].name for i in selected_indices]

        all_rows: List[List[str]] = []
        if os.path.exists("saved_teams.csv"):
            with open("saved_teams.csv", "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                all_rows = [r for r in reader if r and r[0] != team_name]

        all_rows.append(row)

        with open("saved_teams.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(all_rows)

        self.saved_teams = self.load_saved_teams()
        self._refresh_saved_team_listboxes()
        self._showinfo_deferred("Saved", f"Team '{team_name}' saved successfully!")

    # -------------------- LOAD SAVED TEAM --------------------
    def load_saved_team(self, team_number: int) -> None:
        if team_number == 1:
            selection = self.team1_listbox.curselection()
            if not selection:
                return
            team_name = self.team1_listbox.get(selection[0])
            self.loaded_team1_name = team_name
            saved_names = self.saved_teams.get(team_name, [])
            for var, player in zip(self.team1_vars, self.visible_t1):
                var.set(player.name in saved_names)
        else:
            selection = self.team2_listbox.curselection()
            if not selection:
                return
            team_name = self.team2_listbox.get(selection[0])
            self.loaded_team2_name = team_name
            saved_names = self.saved_teams.get(team_name, [])
            for var, player in zip(self.team2_vars, self.visible_t2):
                var.set(player.name in saved_names)

    # -------------------- DISPLAY SELECTED TEAM --------------------
        # Refresh live validation after loading a saved team
        self.update_selection_summary()


    def display_selected_team(self, team: List[Player], title: str) -> None:
        # Replace the checkbox list in the corresponding frame with a simple batting order list,
        # and attach the requested live widgets underneath each team list.
        frame = self.team1_frame if title == "Team 1" else self.team2_frame

        for widget in frame.winfo_children():
            widget.destroy()

        team_name = title
        try:
            if title == "Team 1":
                team_name = (self.loaded_team1_name or "Team 1")
            elif title == "Team 2":
                team_name = (self.loaded_team2_name or "Team 2")
        except Exception:
            team_name = title
        ttk.Label(frame, text=f"{team_name} - Batting Order", anchor="w").pack(anchor="w")
        for idx, p in enumerate(team, start=1):
            line = f"{idx}. {p.name} ({p.batting_rating}/{p.bowling_rating if p.bowling_rating else '-'})"
            ttk.Label(frame, text=line, anchor="w", justify="left").pack(fill="x")

        ttk.Label(frame, text="").pack()

        # Create a single "live" slot under each team. We'll swap its meaning based on who is batting.
        if title == "Team 1":
            self.team1_live_hdr = ttk.Label(frame, text="", font=("TkDefaultFont", 10, "bold"), anchor="w")
            self.team1_live_hdr.pack(anchor="w")
            self.team1_live_body = ttk.Label(frame, text="", font=("TkDefaultFont", 9), anchor="w", justify="left")
            self.team1_live_body.pack(anchor="w")
        else:
            self.team2_live_hdr = ttk.Label(frame, text="", font=("TkDefaultFont", 10, "bold"), anchor="w")
            self.team2_live_hdr.pack(anchor="w")
            self.team2_live_body = ttk.Label(frame, text="", font=("TkDefaultFont", 9), anchor="w", justify="left")
            self.team2_live_body.pack(anchor="w")

    def get_batting_team_name(self) -> str:
        """Return the display name of the team currently batting.

        Uses the match's innings_batting_team mapping, but also respects the
        internal 'team swap' that can occur (e.g. after toss logic) by routing
        through get_display_team_name_for_match_side().
        """
        if hasattr(self, "match") and self.match is not None and hasattr(self.match, "innings_batting_team"):
            tid = self.match.innings_batting_team.get(getattr(self.match, "innings", 1), 1)
            try:
                return self.get_display_team_name_for_match_side(int(tid))
            except Exception:
                return self.loaded_team1_name if tid == 1 else self.loaded_team2_name
        # Fallback for very early states
        inn = getattr(self.match, "innings", 1)
        tid = 1 if inn in (1, 3) else 2
        try:
            return self.get_display_team_name_for_match_side(int(tid))
        except Exception:
            return self.loaded_team1_name if tid == 1 else self.loaded_team2_name
    def declare_innings(self) -> None:
        if not hasattr(self, "match") or self.match is None:
            return
        if getattr(self.match, "match_over", False):
            return
        if not messagebox.askyesno("Declare Innings", "Declare the current innings now?"):
            return
        self.match.declare_innings()

    def _accumulate_series_stats(self, match: 'Match') -> None:
        """Accumulate per-match stats into series aggregates."""
        # Batting
        for p in (self.loaded_team1 + self.loaded_team2):
            # Only count if they batted (balls faced > 0 or were dismissed/retired hurt)
            inns = getattr(p, "innings_balls", 0)
            runs = getattr(p, "innings_runs", 0)
            fours = getattr(p, "innings_fours", 0)
            sixes = getattr(p, "innings_sixes", 0)

            how_out = (getattr(p, "how_out", "") or "").strip()
            dismissed = bool(how_out) and how_out.lower() not in ("not out",)
            # Retired hurt does NOT count as out for averages unless you want it to.
            is_retired_hurt = how_out.lower().startswith("retired hurt")

            if inns == 0 and runs == 0 and not dismissed and not is_retired_hurt:
                continue

            s = self.series_batting_stats.setdefault(p.name, {"runs": 0, "balls": 0, "outs": 0, "fours": 0, "sixes": 0, "inns": 0})
            s["runs"] += int(runs)
            s["balls"] += int(inns)
            s["fours"] += int(fours)
            s["sixes"] += int(sixes)
            s["inns"] += 1
            if dismissed and not is_retired_hurt:
                s["outs"] += 1

        # Bowling: use match bowling figures if present on players
        for p in (self.loaded_team1 + self.loaded_team2):
            # We track only if they have a bowling rating
            if not getattr(p, "bowling_rating", None):
                continue
            balls = getattr(p, "innings_bowled_balls", 0)
            runs = getattr(p, "innings_bowling_runs", 0)
            wkts = getattr(p, "innings_bowling_wickets", 0)
            if balls == 0 and runs == 0 and wkts == 0:
                continue
            s = self.series_bowling_stats.setdefault(p.name, {"balls": 0, "runs": 0, "wkts": 0, "inns": 0})
            s["balls"] += int(balls)
            s["runs"] += int(runs)
            s["wkts"] += int(wkts)
            s["inns"] += 1

    def _show_series_averages_table(self) -> None:
        """Display series batting and bowling averages in a popup window."""
        win = tk.Toplevel(self.root)
        win.title("Series Statistics")
        win.geometry("900x600")

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        # Batting tab
        bat_tab = ttk.Frame(nb)
        nb.add(bat_tab, text="Batting Averages")
        cols = ("Player", "Inns", "Runs", "Outs", "Avg", "SR", "4s", "6s")
        tv = ttk.Treeview(bat_tab, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, anchor="w", width=110 if c == "Player" else 70)
        tv.pack(fill="both", expand=True)

        items = []
        for name, s in self.series_batting_stats.items():
            outs = s["outs"]
            avg = (s["runs"] / outs) if outs > 0 else float("inf")
            sr = (s["runs"] * 100 / s["balls"]) if s["balls"] > 0 else 0.0
            avg_txt = f"{avg:.2f}" if avg != float("inf") else "—"
            items.append((name, s["inns"], s["runs"], outs, avg_txt, f"{sr:.1f}", s["fours"], s["sixes"]))
        # sort by runs desc
        items.sort(key=lambda r: (r[2], r[1]), reverse=True)
        for row in items:
            tv.insert("", "end", values=row)

        # Bowling tab
        bowl_tab = ttk.Frame(nb)
        nb.add(bowl_tab, text="Bowling Averages")
        cols2 = ("Player", "Inns", "Overs", "Runs", "Wkts", "Avg", "Econ")
        tv2 = ttk.Treeview(bowl_tab, columns=cols2, show="headings")
        for c in cols2:
            tv2.heading(c, text=c)
            tv2.column(c, anchor="w", width=130 if c == "Player" else 80)
        tv2.pack(fill="both", expand=True)

        items2 = []
        for name, s in self.series_bowling_stats.items():
            balls = s["balls"]
            overs = balls // 6
            rem = balls % 6
            overs_txt = f"{overs}.{rem}"
            wkts = s["wkts"]
            avg = (s["runs"] / wkts) if wkts > 0 else float("inf")
            econ = (s["runs"] * 6 / balls) if balls > 0 else 0.0
            avg_txt = f"{avg:.2f}" if avg != float("inf") else "—"
            items2.append((name, s["inns"], overs_txt, s["runs"], wkts, avg_txt, f"{econ:.2f}"))
        # sort by wickets desc then avg asc
        items2.sort(key=lambda r: (r[4], -float(r[5].replace("—","inf")) if r[5]!="—" else -1e9), reverse=True)
        for row in items2:
            tv2.insert("", "end", values=row)

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0,10))


    def _prompt_toss_and_start(self, team1: List[Player], team2: List[Player]) -> None:
        """Prompt a coin toss and start a match with the chosen batting/bowling decision."""
        # Determine names
        t1_name = getattr(self, "loaded_team1_name", "Team 1")
        t2_name = getattr(self, "loaded_team2_name", "Team 2")

        # Remember the original selected names for correct result reporting (even if we swap internally)
        self._match_base_team1_name = t1_name
        self._match_base_team2_name = t2_name

        import random
        winner_tid = random.choice([1, 2])
        winner_name = t1_name if winner_tid == 1 else t2_name

        top = tk.Toplevel(self.root)
        top.title("Coin Toss")
        top.transient(self.root)
        top.grab_set()

        msg = ttk.Label(top, text=f"{winner_name} won the toss — what would you like to do?",
                        font=("Arial", 11, "bold"))
        msg.pack(padx=14, pady=(14, 10))

        choice_var = tk.StringVar(value="")

        btn_row = ttk.Frame(top)
        btn_row.pack(padx=14, pady=(0, 14))

        def choose_bat():
            choice_var.set("bat")
            top.destroy()

        def choose_bowl():
            choice_var.set("bowl")
            top.destroy()

        ttk.Button(btn_row, text="Bat", command=choose_bat).pack(side="left", padx=8)
        ttk.Button(btn_row, text="Bowl", command=choose_bowl).pack(side="left", padx=8)

        # Center dialog
        top.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (top.winfo_width() // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (top.winfo_height() // 2)
        top.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.root.wait_window(top)

        choice = choice_var.get() or "bat"
        if choice == "bat":
            batting_first = winner_tid
        else:
            batting_first = 1 if winner_tid == 2 else 2

        # Start match with the chosen batting-first team
                # Ensure the batting-first side is passed as team1 to Match (Match assumes team1 bats first)
        self._current_test_swapped = False
        if batting_first == 2:
            self._current_test_swapped = True
            team1, team2 = team2, team1
            # Keep GUI labels aligned with Match's team ordering for this Test
            try:
                self.loaded_team1, self.loaded_team2 = self.loaded_team2, self.loaded_team1
                self.loaded_team1_name, self.loaded_team2_name = self.loaded_team2_name, self.loaded_team1_name
            except Exception:
                pass
        # Reset per-match one-shot prompts
        self._scorecard_prompted_match_id = None
        
        self.match = Match(team1, team2, self)

        # Enable match controls
        self.declare_button.config(state="normal")
        self.sim_over_button.config(state="normal")

        # Ensure we are showing the current innings tab + live centre panel
        try:
            self.select_innings_tab(1)
        except Exception:
            pass
        try:
            self.update_live_panel()
        except Exception:
            pass

        # Populate initial bowler dropdown for the bowling side
        self.refresh_bowler_dropdown(self.match._bowling_team())

        # Draw scorecards for the first innings
        try:
            self.update_batting_chart(self.match._batting_team())
            self.update_bowling_chart(self.match._bowling_team())
        except Exception:
            pass



    # -------------------- BATTING ORDER EDITOR --------------------
    def _build_team_from_current_selection(self, team_no: int) -> List[Player]:
        """
        Build a team list from the *current* UI selection for Team 1/2, preserving
        saved-team order where applicable.
        """
        if team_no == 1:
            saved_name = getattr(self, "loaded_team1_name", None)
            vars_list = getattr(self, "team1_vars", [])
            visible_players = getattr(self, "visible_t1", [])
        else:
            saved_name = getattr(self, "loaded_team2_name", None)
            vars_list = getattr(self, "team2_vars", [])
            visible_players = getattr(self, "visible_t2", [])

        # If loading a saved team, preserve saved batting order
        if saved_name and hasattr(self, "saved_teams") and saved_name in self.saved_teams:
            ordered_names = self.saved_teams[saved_name]
            name_to_player = {p.name: p for p in visible_players}
            team = [name_to_player[name] for name in ordered_names if name in name_to_player]
        else:
            team = [p for p, v in zip(visible_players, vars_list) if v.get()]
        return team

    def _get_manual_order(self, team_no: int) -> Optional[List[str]]:
        return self.manual_team1_order if team_no == 1 else self.manual_team2_order

    def _set_manual_order(self, team_no: int, ordered_names: List[str]) -> None:
        if team_no == 1:
            self.manual_team1_order = ordered_names
            self._manual_order_sel_snapshot_t1 = set(ordered_names)
        else:
            self.manual_team2_order = ordered_names
            self._manual_order_sel_snapshot_t2 = set(ordered_names)

    def _clear_manual_order_if_selection_changed(self) -> None:
        """
        If the user changes team selection after setting a manual order,
        drop the manual order so we never start a match with a stale order.
        """
        try:
            current_t1 = {p.name for p in self._build_team_from_current_selection(1)}
            if self.manual_team1_order is not None and self._manual_order_sel_snapshot_t1 is not None:
                if current_t1 != self._manual_order_sel_snapshot_t1:
                    self.manual_team1_order = None
                    self._manual_order_sel_snapshot_t1 = None
        except Exception:
            pass

        try:
            current_t2 = {p.name for p in self._build_team_from_current_selection(2)}
            if self.manual_team2_order is not None and self._manual_order_sel_snapshot_t2 is not None:
                if current_t2 != self._manual_order_sel_snapshot_t2:
                    self.manual_team2_order = None
                    self._manual_order_sel_snapshot_t2 = None
        except Exception:
            pass

    def open_batting_order_editor(self, team_no: int) -> None:
        team = self._build_team_from_current_selection(team_no)
        if len(team) < 2:
            self._showinfo_deferred("Batting Order", "Select at least 2 players for this team first.")
            return

        # Start with manual order (if it matches current selection), otherwise current built order
        current_names = [p.name for p in team]
        manual = self._get_manual_order(team_no)
        if manual and set(manual) == set(current_names):
            ordered_names = manual[:]
        else:
            ordered_names = current_names[:]

        win = tk.Toplevel(self.root)
        win.title(f"Edit Batting Order - Team {team_no}")
        win.geometry("420x420")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="Use the buttons to move a player up/down in the batting order.").pack(pady=(10, 6))

        players_by_name = {p.name: p for p in team}
        ordered_players = [players_by_name[n] for n in ordered_names if n in players_by_name]

        def _fmt_player(p: Player) -> str:
            bat = getattr(p, 'batting_rating', '')
            bowl = getattr(p, 'bowling_rating', '')
            wk = ' WK' if getattr(p, 'is_wk', False) else ''
            return f"{p.name}  | Bat {bat}  Bowl {bowl}{wk}"

        lb = tk.Listbox(win, height=16)
        lb.pack(fill="both", expand=True, padx=12)
        for p in ordered_players:
            lb.insert("end", _fmt_player(p))

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=10)

        def move(delta: int) -> None:
            sel = lb.curselection()
            if not sel:
                return
            i = sel[0]
            j = i + delta
            if j < 0 or j >= lb.size():
                return
            val = lb.get(i)
            lb.delete(i)
            lb.insert(j, val)
            lb.selection_clear(0, "end")
            lb.selection_set(j)
            lb.activate(j)

        def apply_and_close() -> None:
            new_order_lines = [lb.get(i) for i in range(lb.size())]
            new_order = [ln.split('  |', 1)[0] for ln in new_order_lines]
            # Persist
            self._set_manual_order(team_no, new_order)

            # Refresh the on-screen batting order display (if we've already replaced checkboxes)
            try:
                players_by_name = {p.name: p for p in team}
                refreshed = [players_by_name[n] for n in new_order if n in players_by_name]
                self.display_selected_team(refreshed, "Team 1" if team_no == 1 else "Team 2")
            except Exception:
                pass

            win.destroy()

        ttk.Button(btn_row, text="Move Up", command=lambda: move(-1)).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Move Down", command=lambda: move(1)).pack(side="left", padx=6)

        bottom_row = ttk.Frame(win)
        bottom_row.pack(pady=(0, 12))

        ttk.Button(bottom_row, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        ttk.Button(bottom_row, text="Apply", command=apply_and_close).pack(side="right", padx=6)


    def start_match(self) -> None:
        def build_team(saved_name: Optional[str], vars_list: List[tk.BooleanVar], visible_players: List[Player]) -> List[Player]:
            # If loading a saved team, preserve saved batting order
            if saved_name and saved_name in self.saved_teams:
                ordered_names = self.saved_teams[saved_name]
                name_to_player = {p.name: p for p in visible_players}
                return [name_to_player[name] for name in ordered_names if name in name_to_player]
            # Otherwise use the selection order as shown
            return [p for p, v in zip(visible_players, vars_list) if v.get()]

        team1 = build_team(self.loaded_team1_name, self.team1_vars, self.visible_t1)
        team2 = build_team(self.loaded_team2_name, self.team2_vars, self.visible_t2)
        # Apply manual batting order overrides (if set and still matches current selection)
        try:
            if self.manual_team1_order and set(self.manual_team1_order) == {p.name for p in team1}:
                by_name = {p.name: p for p in team1}
                team1 = [by_name[n] for n in self.manual_team1_order if n in by_name]
        except Exception:
            pass
        try:
            if self.manual_team2_order and set(self.manual_team2_order) == {p.name for p in team2}:
                by_name = {p.name: p for p in team2}
                team2 = [by_name[n] for n in self.manual_team2_order if n in by_name]
        except Exception:
            pass


        # Initialize series settings on first Test (teams stay the same for the series)
        sel = (self.series_var.get() if hasattr(self, 'series_var') else "Single Test")
        if (not self.series_active) and sel in ("3 Tests", "5 Tests"):
            self.series_active = True
            self.series_total = 3 if sel == "3 Tests" else 5
            self.series_index = 1
            self.series_score = {'team1': 0, 'team2': 0, 'draw': 0, 'tie': 0}
            self.series_team1 = team1
            self.series_team2 = team2
            
            # Freeze series display names (toss may swap per-Test UI labels)
            self.series_base_team1_name = self.loaded_team1_name
            self.series_base_team2_name = self.loaded_team2_name
            self._init_series_aggregates()
            try:
                self.series_menu.config(state="disabled")
            except Exception:
                pass
        elif not self.series_active:
            self.series_total = 1

        if len(team1) != 11 or len(team2) != 11:
            messagebox.showerror("Error", "Both teams must have 11 players")
            return

        # Reset stats for all selected players
        for p in team1 + team2:
            p.reset_match_stats()

        # Replace checkboxes with batting order display
        self.display_selected_team(team1, "Team 1")
        self.display_selected_team(team2, "Team 2")
        # Initialize match (with coin toss)
        # Clear the progress window BEFORE creating the Match, because Match.__init__()
        # calls start_new_day() which prints the day header + conditions.
        self.match_output.delete("1.0", tk.END)
        self.match_output.insert(tk.END, "Match started!\nSelect a bowler and click 'Simulate Over'.\n")

        # Coin toss decides who bats first
        self._prompt_toss_and_start(team1, team2)

        # Hide load-team UI once both teams are locked in
        self.hide_team_load_controls()
        self.update_selection_summary()

        # Switch to the match screen now that teams are locked in
        self.show_match_screen()
    def _reset_series_state(self):
        """Clear all series-related state (Option A: abandon series)."""
        self.series_mode = False
        self.series_total_tests = 0
        self.current_test_number = 1
        self.series_team1 = None
        self.series_team2 = None
        self.series_results = []





    def start_next_test_in_series(self):
        # Reset conclusion-duplicate guard for the new Test
        self._last_concluded_match_id = None
        # (do not touch _handling_match_conclusion here; it guards duplicate callbacks)
        '''Start the next Test in an active series using the same teams.'''
        if not getattr(self, "series_active", False):
            return
        if self.series_index >= self.series_total:
            return
        if self.series_team1 is None or self.series_team2 is None:
            return

        self.series_index += 1

        try:
            self.match_output.delete("1.0", tk.END)
            self.match_output.insert(tk.END, f"Test {self.series_index} of {self.series_total} started!\nSelect a bowler and click 'Simulate Over'.\n")
        except Exception:
            pass

        # Clear all innings scorecards for the new Test (all 4 innings)
        try:
            for txt in getattr(self, 'batting_charts', {}).values():
                txt.delete('1.0', tk.END)
            for txt in getattr(self, 'bowling_charts', {}).values():
                txt.delete('1.0', tk.END)
            # reset notebooks to innings 1
            try:
                self.batting_notebook.select(0)
                self.bowling_notebook.select(0)
            except Exception:
                pass
        except Exception:
            pass


        try:
            self.exit_button.config(state="disabled")
        except Exception:
            pass
        try:
            self.declare_button.config(state="normal")
        except Exception:
            pass

        # Reset per-match stats for the new Test (series aggregates are tracked separately)
        for p in self.series_team1 + self.series_team2:
            p.reset_match_stats()

        # Restore base series names before the toss (so series scoring stays stable)
        try:
            if hasattr(self, "series_base_team1_name") and self.series_base_team1_name:
                self.loaded_team1_name = self.series_base_team1_name
            if hasattr(self, "series_base_team2_name") and self.series_base_team2_name:
                self.loaded_team2_name = self.series_base_team2_name
        except Exception:
            pass

        self.display_selected_team(self.series_team1, "Team 1")
        self.display_selected_team(self.series_team2, "Team 2")
        # IMPORTANT: each Test has its own coin toss
        try:
            self._prompt_toss_and_start(self.series_team1, self.series_team2)
        finally:
            # Never leave the series in a "transitioning" state if something goes wrong starting the next Test.
            self._series_transitioning = False

        if hasattr(self, 'select_innings_tab'):
            self.select_innings_tab(1)
        self.refresh_bowler_dropdown(self.series_team2)
        self.update_batting_chart(self.series_team1)
        self.update_bowling_chart(self.series_team2)

        self._series_transitioning = False
        # Ready to handle conclusion callbacks for the new Test
        self._handling_match_conclusion = False


    def get_display_team_name_for_match_side(self, side: int) -> str:
        """Return the *original* selected team name for the given match side (1 or 2).

        During a Test we may swap teams internally so that Match always treats 'team1' as the batting-first side.
        This helper maps side->name back to the user's original team selections.
        """
        base1 = (getattr(self, "_match_base_team1_name", None)
                 or getattr(self, "series_base_team1_name", None)
                 or getattr(self, "loaded_team1_name", None)
                 or "Team 1")
        base2 = (getattr(self, "_match_base_team2_name", None)
                 or getattr(self, "series_base_team2_name", None)
                 or getattr(self, "loaded_team2_name", None)
                 or "Team 2")
        swapped = bool(getattr(self, "_current_test_swapped", False))
        if swapped:
            return base2 if side == 1 else base1
        return base1 if side == 1 else base2

    def on_match_concluded(self, match_obj=None):
        """Called by Match when the match is finished."""
        # Ignore stale callbacks from a previous Match instance (can happen across series transitions)
        if match_obj is not None and match_obj is not getattr(self, 'match', None):
            return

        # Guard against duplicate callbacks for the same Match instance (Tk can queue multiple).
        current_match = match_obj if match_obj is not None else getattr(self, 'match', None)
        current_match_id = id(current_match) if current_match is not None else None

        # If ball-by-ball playback is in progress, defer conclusion prompts until playback completes.
        try:
            if bool(getattr(self, 'ball_by_ball_enabled', None) and self.ball_by_ball_enabled.get()) and (
                getattr(self, '_ball_by_ball_playing', False) or getattr(self, '_suppress_live_updates', False)
            ):
                self._deferred_match_conclusion = current_match
                self._deferred_match_conclusion_pending = True
                return
        except Exception:
            pass

        if current_match_id is not None and getattr(self, '_last_concluded_match_id', None) == current_match_id:
            return
        self._last_concluded_match_id = current_match_id

        # Guard against duplicate callbacks from queued Tk events
        if getattr(self, '_handling_match_conclusion', False):
            return
        self._handling_match_conclusion = True
        try:
            # If we're transitioning between Tests, we may still receive the *current* match conclusion.
            # Only ignore callbacks that are truly stale.
            if getattr(self, '_series_transitioning', False):
                try:
                    if match_obj is not None and match_obj is getattr(self, 'match', None):
                        # Current match just finished; proceed and clear the transition flag.
                        self._series_transitioning = False
                    else:
                        return
                except Exception:
                    return

            try:
                self.exit_button.config(state="normal")
            except Exception:
                pass

            # Offer to save the completed scorecard (once per Test).
            # In a multi-Test series where another Test remains, saving is handled in the combined prompt below.
            try:
                in_series = bool(getattr(self, 'series_active', False) and getattr(self, 'series_total', 1) > 1)
                has_next = bool(in_series and getattr(self, 'series_index', 1) < getattr(self, 'series_total', 1))
                if not has_next:
                    if messagebox.askyesno("Save scorecard", "The match has concluded. Would you like to save the scorecard?"):
                        self._prompt_save_scorecard_deferred()
            except Exception:
                pass

            # Series bookkeeping
            try:
                if getattr(self, "series_active", False) and getattr(self, "series_total", 1) > 1:

                    # Update series aggregates (batting/bowling) from the completed Test
                    try:
                        self._accumulate_series_from_match(getattr(self, "match", None))
                    except Exception:
                        pass

                    res = getattr(getattr(self, "match", None), "result_summary", None)

                    # Map result winner to the *base* series teams (coin toss may swap UI labels per Test)
                    swapped = bool(getattr(self, "_current_test_swapped", False))
                    winner = None
                    if res and res.get("type") == "win":
                        winner = int(res.get("winner") or 0)
                        if swapped and winner in (1, 2):
                            winner = 1 if winner == 2 else 2

                        if winner == 1:
                            self.series_score["team1"] += 1
                        elif winner == 2:
                            self.series_score["team2"] += 1
                    elif res and res.get("type") == "tie":
                        self.series_score["tie"] += 1
                    else:
                        self.series_score["draw"] += 1

                    t1 = (getattr(self, "series_base_team1_name", None) or self.loaded_team1_name or "Team 1")
                    t2 = (getattr(self, "series_base_team2_name", None) or self.loaded_team2_name or "Team 2")

                    # Prevent duplicate series-update popups for the same Test (can happen if multiple
                    # end-of-match callbacks get queued in Tk)
                    if getattr(self, '_last_series_update_test_index', None) == self.series_index:
                        return
                    self._last_series_update_test_index = self.series_index

                    msg = (f"Series update (after Test {self.series_index} of {self.series_total}):\n"
                           f"{t1}: {self.series_score['team1']}\n"
                           f"{t2}: {self.series_score['team2']}\n"
                           f"Draws: {self.series_score['draw']}\n"
                           f"Ties: {self.series_score['tie']}")

                    if self.series_index < self.series_total:
                        next_no = self.series_index + 1
                        msg2 = msg + f"\n\nSave scorecard and proceed to Test {next_no} of {self.series_total}?"
                        go_with_save = False
                        try:
                            go_with_save = bool(messagebox.askyesno("Series", msg2))
                        except Exception:
                            go_with_save = False
                        if go_with_save:
                            try:
                                self._prompt_save_scorecard_deferred()
                            except Exception:
                                pass
                        # Transition to next Test (either way)
                        self._series_transitioning = True
                        try:
                            self.root.after(0, self.start_next_test_in_series)
                        except Exception:
                            self.start_next_test_in_series()
                        return
                    else:
                        # Final Test finished: scorecard-save prompt already shown earlier when the match concluded.
                        # Now show series averages with save option.

                        try:
                            self.show_series_averages_window(title=f"{t1} vs {t2} - Series Averages")
                        except Exception:
                            pass

                        try:
                            self._showinfo_deferred("Series", msg + "\nSeries complete.")
                        except Exception:
                            pass

                        try:
                            self.series_menu.config(state="readonly")
                        except Exception:
                            pass

                        self.series_active = False

            except Exception:
                pass
        finally:
            # Always release guard for future matches/tests unless we're mid-transition (handled above)
            if not getattr(self, '_series_transitioning', False):
                self._handling_match_conclusion = False

    def _default_scorecard_filename(self) -> str:
        t1 = (self.loaded_team1_name or "Team 1").strip()
        t2 = (self.loaded_team2_name or "Team 2").strip()
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        test_tag = ""
        try:
            if getattr(self, "series_active", False) and getattr(self, "series_total", 1) > 1:
                test_tag = f" - Test {getattr(self, 'series_index', 1)}"
        except Exception:
            test_tag = ""
        base = f"{t1} vs {t2}{test_tag} {today}"
        # Windows/macOS safe filename
        base = re.sub(r'[<>:"/\\|?*]+', "", base)
        base = re.sub(r"\s+", " ", base).strip()
        return base + ".txt"

    def build_scorecard_text(self) -> str:
        t1 = self.loaded_team1_name or "Team 1"
        t2 = self.loaded_team2_name or "Team 2"
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        parts = []
        parts.append(f"{t1} vs {t2}  ({today})")
        parts.append("=" * 60)
        parts.append("")
        parts.append("MATCH PROGRESS")
        parts.append("-" * 60)
        try:
            parts.append(self.match_output.get("1.0", tk.END).rstrip())
        except Exception:
            pass

        for inn in (1, 2, 3, 4):
            parts.append("")
            parts.append("=" * 60)
            parts.append(f"INNINGS {inn} - BATTING")
            parts.append("-" * 60)
            try:
                txt = self.batting_charts[inn].get("1.0", tk.END).rstrip()
                parts.append(txt)
            except Exception:
                parts.append("(not available)")
            parts.append("")
            parts.append(f"INNINGS {inn} - BOWLING")
            parts.append("-" * 60)
            try:
                txt = self.bowling_charts[inn].get("1.0", tk.END).rstrip()
                parts.append(txt)
            except Exception:
                parts.append("(not available)")

        parts.append("")
        return "\n".join(parts)

    # -------------------- SERIES AGGREGATES (BATTING + BOWLING) --------------------
    def _init_series_aggregates(self) -> None:
        """Initialise (or reset) series aggregates. Called at the start of a multi-Test series."""
        self.series_batting_agg = {}  # name -> dict
        self.series_bowling_agg = {}  # name -> dict

    def _accumulate_series_from_match(self, match_obj) -> None:
        """Accumulate batting/bowling stats from a completed Match into series aggregates."""
        if not match_obj:
            return

        innings_summaries = getattr(match_obj, "innings_summaries", {}) or {}
        for _inn, summ in innings_summaries.items():
            # Batting
            for row in (summ.get("batting_rows") or []):
                name = row.get("name")
                if not name:
                    continue
                runs = int(row.get("runs", 0) or 0)
                balls = int(row.get("balls", 0) or 0)
                fours = int(row.get("fours", 0) or 0)
                sixes = int(row.get("sixes", 0) or 0)
                how_out = str(row.get("how_out", "") or "").strip()
                how_out_l = how_out.lower()

                # Did this innings count?
                batted = (balls > 0) or (runs > 0) or bool(how_out)
                if not batted:
                    continue

                out = 0
                if how_out and how_out_l not in ("not out",):
                    # retired hurt does not count as out for averages
                    if "retired" not in how_out_l:
                        out = 1

                rec = self.series_batting_agg.get(name)
                if rec is None:
                    rec = {"name": name, "inn": 0, "outs": 0, "runs": 0, "balls": 0, "4s": 0, "6s": 0, "hs": 0}
                    self.series_batting_agg[name] = rec

                rec["inn"] += 1
                rec["outs"] += out
                rec["runs"] += runs
                rec["balls"] += balls
                rec["4s"] += fours
                rec["6s"] += sixes
                if runs > rec["hs"]:
                    rec["hs"] = runs

            # Bowling
            for row in (summ.get("bowling_rows") or []):
                name = row.get("name")
                if not name:
                    continue
                overs = int(row.get("overs", 0) or 0)
                runs_c = int(row.get("runs", 0) or 0)
                wkts = int(row.get("wkts", 0) or 0)
                if overs <= 0 and runs_c <= 0 and wkts <= 0:
                    continue

                rec = self.series_bowling_agg.get(name)
                if rec is None:
                    rec = {"name": name, "overs": 0, "balls": 0, "runs": 0, "wkts": 0}
                    self.series_bowling_agg[name] = rec

                rec["overs"] += overs
                rec["balls"] += overs * 6
                rec["runs"] += runs_c
                rec["wkts"] += wkts

    def _build_series_averages_text(self) -> str:
        """Return a formatted text report of series batting + bowling averages."""
        lines = []
        t1 = (getattr(self, "series_base_team1_name", None) or self.loaded_team1_name or "Team 1")
        t2 = (getattr(self, "series_base_team2_name", None) or self.loaded_team2_name or "Team 2")
        lines.append(f"SERIES AVERAGES: {t1} vs {t2}")
        lines.append("=" * 70)
        lines.append("")

        # ---- Batting ----
        lines.append("BATTING")
        lines.append("-" * 70)
        header = f"{'Player':26} {'Inns':>4} {'Runs':>5} {'Out':>3} {'Avg':>6} {'SR':>6} {'HS':>4} {'4s':>4} {'6s':>4}"
        lines.append(header)
        lines.append("-" * 70)

        bat_rows = list((self.series_batting_agg or {}).values())
        bat_rows.sort(key=lambda r: (int(r.get("runs", 0) or 0), -int(r.get("outs", 0) or 0)), reverse=True)

        def fmt_avg(runs, outs):
            if outs <= 0:
                return "—"
            return f"{(runs/outs):.2f}"

        def fmt_sr(runs, balls):
            if balls <= 0:
                return "—"
            return f"{(runs/balls*100):.1f}"

        for r in bat_rows:
            name = str(r.get("name", ""))[:26]
            inns = int(r.get("inn", 0) or 0)
            runs = int(r.get("runs", 0) or 0)
            outs = int(r.get("outs", 0) or 0)
            balls = int(r.get("balls", 0) or 0)
            hs = int(r.get("hs", 0) or 0)
            fours = int(r.get("4s", 0) or 0)
            sixes = int(r.get("6s", 0) or 0)
            lines.append(f"{name:26} {inns:>4} {runs:>5} {outs:>3} {fmt_avg(runs, outs):>6} {fmt_sr(runs, balls):>6} {hs:>4} {fours:>4} {sixes:>4}")

        if not bat_rows:
            lines.append("(no batting data)")

        lines.append("")
        # ---- Bowling ----
        lines.append("BOWLING")
        lines.append("-" * 70)
        header = f"{'Player':26} {'Overs':>5} {'Runs':>5} {'Wkts':>4} {'Avg':>6} {'Econ':>6}"
        lines.append(header)
        lines.append("-" * 70)

        bowl_rows = list((self.series_bowling_agg or {}).values())
        # sort by wickets, then average (lower better)
        def bowl_sort_key(r):
            wk = int(r.get("wkts", 0) or 0)
            runs = int(r.get("runs", 0) or 0)
            avg = (runs / wk) if wk > 0 else 10**9
            return (wk, -avg)

        bowl_rows.sort(key=bowl_sort_key, reverse=True)

        def fmt_bavg(runs, wkts):
            if wkts <= 0:
                return "—"
            return f"{(runs/wkts):.2f}"

        def fmt_econ(runs, balls):
            if balls <= 0:
                return "—"
            return f"{(runs/(balls/6)):.2f}"

        for r in bowl_rows:
            name = str(r.get("name", ""))[:26]
            overs = int(r.get("overs", 0) or 0)
            balls = int(r.get("balls", 0) or 0)
            runs = int(r.get("runs", 0) or 0)
            wkts = int(r.get("wkts", 0) or 0)
            lines.append(f"{name:26} {overs:>5} {runs:>5} {wkts:>4} {fmt_bavg(runs, wkts):>6} {fmt_econ(runs, balls):>6}")

        if not bowl_rows:
            lines.append("(no bowling data)")

        lines.append("")
        return "\n".join(lines)

    def show_series_averages_window(self, title: str = "Series Averages") -> None:
        """Popup window showing series batting + bowling averages, with save option."""
        top = tk.Toplevel(self.root)
        top.title(title)
        top.transient(self.root)

        frm = ttk.Frame(top)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        txt = tk.Text(frm, width=92, height=32, wrap="none")
        txt.pack(side="left", fill="both", expand=True)

        ysb = ttk.Scrollbar(frm, orient="vertical", command=txt.yview)
        ysb.pack(side="right", fill="y")
        txt.configure(yscrollcommand=ysb.set)

        report = self._build_series_averages_text()
        txt.insert("1.0", report)
        txt.config(state="disabled")

        btns = ttk.Frame(top)
        btns.pack(fill="x", padx=10, pady=(0, 10))

        def do_save():
            default_name = "series_averages.txt"
            try:
                t1 = (getattr(self, "series_base_team1_name", None) or self.loaded_team1_name or "Team 1")
                t2 = (getattr(self, "series_base_team2_name", None) or self.loaded_team2_name or "Team 2")
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                base = f"{t1} vs {t2} - Series Averages {today}"
                base = re.sub(r'[<>:"/\\|?*]+', "", base)
                base = re.sub(r"\s+", " ", base).strip()
                default_name = base + ".txt"
            except Exception:
                pass

            save_path = filedialog.asksaveasfilename(
                title="Save series averages",
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text file", "*.txt"), ("All files", "*.*")]
            )
            if not save_path:
                return
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report)
                self._showinfo_deferred("Saved", f"Series averages saved to:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Save failed", f"Could not save file:\n{e}")

        ttk.Button(btns, text="Save Averages", command=do_save).pack(side="left")
        ttk.Button(btns, text="Close", command=top.destroy).pack(side="right")

    def prompt_save_scorecard(self) -> None:
        # Guard against duplicate prompts for the same match
        match_id = id(getattr(self, 'match', None))
        if match_id and getattr(self, '_scorecard_prompted_match_id', None) == match_id:
            return
        self._scorecard_prompted_match_id = match_id
        default_name = self._default_scorecard_filename()
        path = filedialog.asksaveasfilename(
            title="Save scorecard",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        self.save_scorecard_to_file(path)

    def save_scorecard_to_file(self, path: str) -> None:
        content = self.build_scorecard_text()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            self._showinfo_deferred("Saved", f"Scorecard saved to:\n{path}")
        except Exception:
            pass

    pass

    def exit_match(self):
        """Return to the Team Selection screen (only after match concludes)."""
        if getattr(self, "match", None) is not None and not getattr(self.match, "match_over", False):
            return

        # Rebuild the UI from scratch on the same root window
        try:
            for w in list(self.root.winfo_children()):
                w.destroy()
        except Exception:
            pass

        CricketGUI(self.root)
    # -------------------- SIMULATE OVER --------------------
    def simulate_over(self) -> None:
        if getattr(self, "_ball_by_ball_playing", False):
            return

        if not hasattr(self, "match") or self.match is None:
            messagebox.showerror("Error", "Start the match first")
            return

        bowler_display = self.bowler_var.get()
        bowler = getattr(self, "_bowler_display_to_name", {}).get(bowler_display, bowler_display)
        if not bowler_display or not bowler:
            messagebox.showerror("Error", "Select a bowler")
            return

        # Rebuild dropdown (filters out ineligible bowlers) and hard-guard
        bowling_team = self.match._bowling_team()
        self.refresh_bowler_dropdown(bowling_team)
        try:
            can_bowl = (self.match._bowler_can_bowl_name(bowler)
                        if hasattr(self.match, "_bowler_can_bowl_name")
                        else self.match._bowler_can_bowl(next((p for p in self.match._bowling_team() if p.name == bowler), None)))
        except Exception:
            can_bowl = True

        if not can_bowl:
            messagebox.showwarning(
                "Bowler not eligible",
                "That bowler has reached their session/day limit (or cannot bowl consecutive overs)."
            )
            return

        # Ball-by-ball mode: simulate immediately (so stats/state are correct), then replay output with a delay.
        if hasattr(self, "ball_by_ball_enabled") and bool(self.ball_by_ball_enabled.get()):
            try:
                self._ball_by_ball_playing = True
                self._suppress_live_updates = True
                try:
                    self.sim_over_button.config(state="disabled")
                except Exception:
                    pass

                captured: list[str] = []
                original_insert = self.match_output.insert

                def _capture_insert(index, chars, *args):
                    try:
                        captured.append(str(chars))
                    except Exception:
                        pass

                # Capture all match_output inserts during simulation
                self.match_output.insert = _capture_insert  # type: ignore[assignment]
                try:
                    self.match.start_over(bowler)
                finally:
                    self.match_output.insert = original_insert  # type: ignore[assignment]

                # Refresh bowler list after the over (limits may have changed)
                try:
                    self.refresh_bowler_dropdown(self.match._bowling_team())
                except Exception:
                    pass

                # Replay captured output line-by-line
                chunks: list[str] = []
                for piece in captured:
                    if not piece:
                        continue
                    chunks.extend(piece.splitlines(True) if "\n" in piece else [piece])

                self._play_ball_by_ball(chunks, 0)
                return
            except Exception:
                # Fallback to normal mode if anything goes wrong
                try:
                    self._ball_by_ball_playing = False
                    self.sim_over_button.config(state="normal")
                    self._suppress_live_updates = False
                except Exception:
                    pass

        # Normal mode (instant)
        self._suppress_live_updates = False
        self.match.start_over(bowler)

        # Refresh bowler list after the over (limits may have changed)
        try:
            self.refresh_bowler_dropdown(self.match._bowling_team())
        except Exception:
            pass


    def toggle_ball_by_ball(self) -> None:
        """Toggle ball-by-ball playback on/off."""
        try:
            new_val = not bool(self.ball_by_ball_enabled.get())
            self.ball_by_ball_enabled.set(new_val)
        except Exception:
            new_val = False

        try:
            self.ball_by_ball_toggle_btn.config(text=("ON" if new_val else "OFF"))
        except Exception:
            pass

        if not new_val:
            try:
                self.ball_by_ball_text_var.set("")
                self._apply_ticker_style("")
            except Exception:
                pass


    def _ball_by_ball_delay_ms(self) -> int:
        """Return the per-step delay (ms) for ball-by-ball playback."""
        try:
            speed = str(self.ball_by_ball_speed_var.get() or "Medium").strip().lower()
        except Exception:
            speed = "medium"

        if speed == "slow":
            return 800
        if speed == "fast":
            return 400
        # medium default
        return 600

    def _ticker_is_wicket_line(self, line: str) -> bool:
        """Return True if the ticker line represents a wicket/dismissal."""
        try:
            s = (line or "").strip().lower()
        except Exception:
            return False
        if not s:
            return False
        # Common wicket markers in commentary lines
        if "wicket" in s:
            return True
        if " is out" in s:
            return True
        if "run out" in s or "lbw" in s or "bowled" in s or "stumped" in s or "caught" in s:
            return True
        if "retired hurt" in s:
            return True
        # Avoid false positives like "Not Out"
        if "not out" in s:
            return False
        return False

    def _apply_ticker_style(self, line: str) -> None:
        """Switch ticker style so wicket balls show in red."""
        try:
            style = "BallByBallWicket.TEntry" if self._ticker_is_wicket_line(line) else "BallByBall.TEntry"
            self.ball_by_ball_entry.configure(style=style)
        except Exception:
            pass

    def _run_deferred_match_conclusion(self) -> None:
        """Run any deferred match conclusion prompt after ball-by-ball playback completes."""
        try:
            if not getattr(self, '_deferred_match_conclusion_pending', False):
                return
            match_obj = getattr(self, '_deferred_match_conclusion', None)
            self._deferred_match_conclusion_pending = False
            self._deferred_match_conclusion = None
            # Safe to run conclusion logic now
            self.on_match_concluded(match_obj)
        except Exception:
            pass

    def _play_ball_by_ball(self, chunks: list[str], idx: int = 0) -> None:
        """Replay previously captured match output in timed steps."""
        if idx >= len(chunks):
            # Done
            try:
                self._ball_by_ball_playing = False
            except Exception:
                pass
            # Now that playback has caught up, allow live updates again and refresh the top panel
            try:
                self._suppress_live_updates = False
            except Exception:
                pass
            try:
                self.update_live_panel()
            except Exception:
                pass
            # Refresh bottom scorecards now that playback is complete
            try:
                if hasattr(self, "match") and self.match is not None:
                    self.update_batting_chart(self.match._batting_team())
                    self.update_bowling_chart(self.match._bowling_team())
            except Exception:
                pass
            try:
                self.sim_over_button.config(state="normal")
            except Exception:
                pass
            try:
                self._run_deferred_match_conclusion()
            except Exception:
                pass
            return

        chunk = chunks[idx]
        try:
            self.match_output.insert(tk.END, chunk)
            self.match_output.see(tk.END)
        except Exception:
            pass

        # Update the single-line commentary box with the most recent non-empty line.
        try:
            cleaned = str(chunk).replace("\r", "").strip("\n")
            if cleaned.strip():
                # Keep it one line
                cleaned = cleaned.split("\n")[-1].strip()
                self.ball_by_ball_text_var.set(cleaned[:200])
                self._apply_ticker_style(cleaned)
        except Exception:
            pass

        delay = self._ball_by_ball_delay_ms()
        try:
            self.root.after(delay, lambda: self._play_ball_by_ball(chunks, idx + 1))
        except Exception:
            # If after() fails for some reason, finish instantly
            self._play_ball_by_ball(chunks, len(chunks))

    def refresh_bowler_dropdown(self, bowling_team: List[Player]) -> None:
        """Populate the 'Select bowler for over' dropdown with only eligible bowlers.

        Enhancement: show bowling rating in brackets next to the name, e.g. "NJ Astle (C)".
        Internally we keep a mapping from display string -> real player name.
        """
        if not hasattr(self, "match") or self.match is None:
            self.bowler_menu["values"] = []
            self.bowler_var.set("")
            self._bowler_display_to_name = {}
            return

        max_overs_per_bowler_session = 2
        max_overs_per_bowler_day = 4

        eligible_display: List[str] = []
        display_to_name: Dict[str, str] = {}

        for p in bowling_team:
            if not getattr(p, "bowling_rating", None):
                continue
            name = p.name
            if self.match.bowler_overs_session.get(name, 0) >= max_overs_per_bowler_session:
                continue
            if self.match.bowler_overs_today.get(name, 0) >= max_overs_per_bowler_day:
                continue
            if self.match.last_bowler == name:
                continue

            disp = f"{name} ({p.bowling_rating})"
            eligible_display.append(disp)
            display_to_name[disp] = name

        self._bowler_display_to_name = display_to_name
        self.bowler_menu["values"] = eligible_display

        cur = self.bowler_var.get()
        # If current selection is a raw name (older state), upgrade it to display string if possible
        if cur and cur in {v for v in display_to_name.values()}:
            for d, n in display_to_name.items():
                if n == cur:
                    cur = d
                    break

        if cur not in eligible_display:
            self.bowler_var.set(eligible_display[0] if eligible_display else "")
        else:
            self.bowler_var.set(cur)

    # -------------------- UPDATE SCORE --------------------

    def update_score(self, runs: int, wickets: int, extras: int = 0) -> None:
        """Update score display.
        Note: We intentionally do NOT append the running score to the match progress/ticker each ball.
        The main score views update at the end of the over / via the live panel refresh."""
        try:
            # If you later add a dedicated score label, update it here.
            pass
        except Exception:
            pass

        try:
            return int(self.match.innings)
        except Exception:
            return 1

    def select_innings_tab(self, innings_num: int) -> None:
        try:
            self.batting_notebook.select(innings_num - 1)
        except Exception:
            pass
        try:
            self.bowling_notebook.select(innings_num - 1)
        except Exception:
            pass

    def update_live_panel(self) -> None:
        if not hasattr(self, "match") or self.match is None:
            return

        if getattr(self, '_suppress_live_updates', False):
            return

        team_name = self.get_batting_team_name()
        runs = getattr(self.match, "runs", 0)
        wkts = getattr(self.match, "wickets_taken", 0)
        try:
            if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
                self.live_canvas.itemconfig(self._live_items.get('title'), text=f"{team_name}   {wkts} / {runs}")
        except Exception:
            pass

        bats = getattr(self.match, "current_batsmen", []) or []
        header = f"{'Batsman':<18} {'R':>3} {'B':>3} {'4s':>3} {'6s':>3}"

        def fmt_bat(p):
            return f"{p.name:<18} {p.runs:>3} {p.balls_faced:>3} {p.fours:>3} {p.sixes:>3}"

        # Header is a separate label so we can make it bold consistently
        if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
            try:
                self.live_canvas.itemconfig(self._live_items.get('bat_hdr'), text=header)
            except Exception:
                pass

        if len(bats) >= 1:
            try:
                if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
                    self.live_canvas.itemconfig(self._live_items.get('bat1'), text=fmt_bat(bats[0]))
            except Exception:
                pass
        else:
            try:
                if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
                    self.live_canvas.itemconfig(self._live_items.get('bat1'), text="")
            except Exception:
                pass

        if len(bats) >= 2:
            try:
                if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
                    self.live_canvas.itemconfig(self._live_items.get('bat2'), text=fmt_bat(bats[1]))
            except Exception:
                pass
        else:
            try:
                if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
                    self.live_canvas.itemconfig(self._live_items.get('bat2'), text="")
            except Exception:
                pass

        fow = getattr(self.match, "fow", []) or []
        last_fow_runs = fow[-1][1] if fow else 0

        partnership_runs = max(0, runs - last_fow_runs)
        partnership_balls = 0
        try:
            partnership_balls = sum(getattr(p, "balls_faced", 0) for p in bats[:2])
        except Exception:
            partnership_balls = 0
        partnership_str = f"{partnership_runs} runs ({partnership_balls} balls)"

        # Current bowler string
        bowler = getattr(self.match, "bowler", None)
        if bowler:
            ob = getattr(bowler, "overs_bowled", 0)
            balls = getattr(self.match, "current_over_legal_balls", 0)
            overs_txt = f"{ob}.{balls}" if balls else f"{ob}.0"
            bowler_str = f"{bowler.name}   {bowler.wickets}-{bowler.runs_conceded} ({overs_txt})"
        else:
            bowler_str = ""

        # Determine which team is batting (1 or 2) to swap the left/right live slots
        innings = getattr(self.match, "innings", 1)
        bt = None
        if hasattr(self.match, "innings_batting_team"):
            try:
                bt = self.match.innings_batting_team.get(innings, 1 if innings in (1, 3) else 2)
            except Exception:
                bt = None
        if bt is None:
            bt = 1 if innings in (1, 3) else 2

        # Team 1 live slot
        if hasattr(self, "team1_live_hdr") and hasattr(self, "team1_live_body"):
            if bt == 1:
                self.team1_live_hdr.config(text="CURRENT PARTNERSHIP")
                self.team1_live_body.config(text=partnership_str)
            else:
                self.team1_live_hdr.config(text="CURRENT BOWLER")
                self.team1_live_body.config(text=bowler_str)

        # Team 2 live slot
        if hasattr(self, "team2_live_hdr") and hasattr(self, "team2_live_body"):
            if bt == 2:
                self.team2_live_hdr.config(text="CURRENT PARTNERSHIP")
                self.team2_live_body.config(text=partnership_str)
            else:
                self.team2_live_hdr.config(text="CURRENT BOWLER")
                self.team2_live_body.config(text=bowler_str)

        # Match situation (lead / trail / required) (centre panel)
        situation_lines = []
        if hasattr(self.match, "innings_summaries") and hasattr(self.match, "innings_batting_team"):
            bt_map = self.match.innings_batting_team.get(innings, bt)
            if hasattr(self.match, "totals_by_team_including_current"):
                t1, t2 = self.match.totals_by_team_including_current()
            else:
                t1 = t2 = 0
                for inn, summ in getattr(self.match, "innings_summaries", {}).items():
                    rr = int(summ.get("runs", 0) or 0)
                    tid = self.match.innings_batting_team.get(int(inn), 1 if int(inn) in (1, 3) else 2)
                    if tid == 1:
                        t1 += rr
                    else:
                        t2 += rr
                if bt_map == 1:
                    t1 += runs
                else:
                    t2 += runs

            batting_total = t1 if bt_map == 1 else t2
            other_total = t2 if bt_map == 1 else t1

            if innings == 4:
                required = other_total - batting_total + 1
                if required > 0:
                    situation_lines.append(f"Required: {required} runs")
                else:
                    lead = batting_total - other_total
                    situation_lines.append(f"Lead: {lead} runs")
            else:
                diff = batting_total - other_total
                if diff > 0:
                    situation_lines.append(f"Lead: {diff} runs")
                elif diff < 0:
                    situation_lines.append(f"Trail: {abs(diff)} runs")
                else:
                    situation_lines.append("Scores level")

        if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
            try:
                self.live_canvas.itemconfig(self._live_items.get('sit'), text="  ".join(situation_lines) if situation_lines else "")
            except Exception:
                pass

        # Overs remaining in session / day
        try:
            over_in_day = int(getattr(self.match, "overs_in_day", 0) or 0)
            day_sched = int(getattr(self.match, "day_overs_scheduled", getattr(self.match, "DAY_OVERS", 16)) or 16)
            day_rem = max(0, day_sched - over_in_day)

            sess_done = int(getattr(self.match, "session_overs_completed", 0) or 0)
            sess_len = int(getattr(self.match, "overs_per_session", 8) or 8)
            sess_rem = max(0, sess_len - sess_done)
            sess_no = int(getattr(self.match, "session_number", 1) or 1)
            day_no = getattr(getattr(self, "match", None), "current_day", 1)

            time_text = f"Session {sess_no}: {sess_rem} overs remain | Day {day_no}: {day_rem} overs remain"

            # Optional label (if present)
            if hasattr(self, "live_time"):
                try:
                    self.live_time.config(text=time_text)
                except Exception:
                    pass

            # Visible canvas line under MATCH SITUATION
            if hasattr(self, 'live_canvas') and getattr(self, '_live_items', None):
                try:
                    self.live_canvas.itemconfig(self._live_items.get('time'), text=time_text)
                except Exception:
                    pass
        except Exception:
            if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
                try:
                    self.live_canvas.itemconfig(self._live_items.get('time'), text="")
                except Exception:
                    pass

        # Fall of wickets (centre panel)
        if hasattr(self,'live_canvas') and getattr(self,'_live_items',None):
            try:
                self.live_canvas.itemconfig(self._live_items.get('fow'), text=", ".join([f"{w}-{r}" for (w, r) in fow]) if fow else "")
            except Exception:
                pass
        # Keep the canvas background/layout in sync
        try:
            if hasattr(self, '_render_live_canvas'):
                self._render_live_canvas()
        except Exception:
            pass


    def render_innings_scorecards(self, innings_num: int, summary: Dict[str, Any]) -> None:
        bat_chart = self.batting_charts.get(innings_num)
        bowl_chart = self.bowling_charts.get(innings_num)

        if bat_chart is not None:
            bat_chart.delete("1.0", tk.END)
            w_bat, w_how, w_runs, w_balls, w_4s, w_6s = 14, 42, 6, 7, 4, 4
            bat_chart.insert(tk.END, f"{'Batsman':<{w_bat}}{'How out':<{w_how}}{'Runs':<{w_runs}}{'Balls':<{w_balls}}{'4s':<{w_4s}}{'6s':<{w_6s}}\n")
            for row in summary.get("batting_rows", []):
                bat_chart.insert(tk.END,
                    f"{row.get('name',''):<{w_bat}}"
                    f"{row.get('how_out',''):<{w_how}}"
                    f"{str(row.get('runs',0)):<{w_runs}}"
                    f"{str(row.get('balls',0)):<{w_balls}}"
                    f"{str(row.get('fours',0)):<{w_4s}}"
                    f"{str(row.get('sixes',0)):<{w_6s}}\n"
                )
            bat_chart.insert(tk.END, f"Extras (b {summary.get('extras_b',0)}, lb {summary.get('extras_lb',0)}, nb {summary.get('extras_nb',0)}, w {summary.get('extras_w',0)})\n")
            bat_chart.insert(tk.END, f"TOTAL   {summary.get('wickets',0)} wickets   {summary.get('runs',0)} runs\n")

        if bowl_chart is not None:
            bowl_chart.delete("1.0", tk.END)
            w_bowl, w_ov, w_r, w_w = 18, 8, 8, 6
            bowl_chart.insert(tk.END, f"{'Bowler':<{w_bowl}}{'Overs':<{w_ov}}{'Runs':<{w_r}}{'Wkts':<{w_w}}\n")
            for row in summary.get("bowling_rows", []):
                bowl_chart.insert(tk.END,
                    f"{row.get('name',''):<{w_bowl}}"
                    f"{str(row.get('overs',0)):<{w_ov}}"
                    f"{str(row.get('runs',0)):<{w_r}}"
                    f"{str(row.get('wkts',0)):<{w_w}}\n"
                )

    def update_batting_chart(self, team: List[Player]) -> None:
        # During ball-by-ball playback we suppress live scorecard refreshes so they only
        # update once the over has fully replayed.
        if getattr(self, "_suppress_live_updates", False) and hasattr(self, "ball_by_ball_enabled") and bool(self.ball_by_ball_enabled.get()):
            return

        inn = self._current_innings_num()
        chart = self.batting_charts.get(inn)
        if chart is None:
            return
        chart.delete("1.0", tk.END)

        w_bat = 22
        w_how = 42
        w_runs = 6
        w_balls = 7
        w_4s = 4
        w_6s = 4

        header = (
            f"{'Batsman':<{w_bat}}"
            f"{'How out':<{w_how}}"
            f"{'Runs':<{w_runs}}"
            f"{'Balls':<{w_balls}}"
            f"{'4s':<{w_4s}}"
            f"{'6s':<{w_6s}}"
            "\n"
        )
        chart.insert(tk.END, header)

        for p in team:
            how_out = p.how_out
            if not how_out and (p.balls_faced > 0 or p.runs > 0):
                how_out = "not out"
            row = (
                f"{p.name:<{w_bat}}"
                f"{how_out:<{w_how}}"
                f"{str(p.runs):<{w_runs}}"
                f"{str(p.balls_faced):<{w_balls}}"
                f"{str(p.fours):<{w_4s}}"
                f"{str(p.sixes):<{w_6s}}"
                "\n"
            )
            chart.insert(tk.END, row)

        extras_b = getattr(self.match, "extras_b", 0) if self.match else 0
        extras_lb = getattr(self.match, "extras_lb", 0) if self.match else 0
        extras_nb = getattr(self.match, "extras_nb", 0) if self.match else 0
        extras_w = getattr(self.match, "extras_w", 0) if self.match else 0
        chart.insert(tk.END, f"Extras (b {extras_b}, lb {extras_lb}, nb {extras_nb}, w {extras_w})\n")
        if self.match:
            chart.insert(tk.END, f"TOTAL   {self.match.wickets_taken} wickets   {self.match.runs} runs\n")

        self.select_innings_tab(inn)


    def update_bowling_chart(self, team: List[Player]) -> None:
        # During ball-by-ball playback we suppress live scorecard refreshes so they only
        # update once the over has fully replayed.
        if getattr(self, "_suppress_live_updates", False) and hasattr(self, "ball_by_ball_enabled") and bool(self.ball_by_ball_enabled.get()):
            return

        inn = self._current_innings_num()
        chart = self.bowling_charts.get(inn)
        if chart is None:
            return
        chart.delete("1.0", tk.END)

        w_bowl = 18
        w_ov = 8
        w_r = 8
        w_w = 6

        header = (
            f"{'Bowler':<{w_bowl}}"
            f"{'Overs':<{w_ov}}"
            f"{'Runs':<{w_r}}"
            f"{'Wkts':<{w_w}}"
            "\n"
        )
        chart.insert(tk.END, header)

        for p in team:
            if not str(getattr(p, "bowling_rating", "") or "").strip():
                continue
            row = (
                f"{p.name:<{w_bowl}}"
                f"{str(getattr(p, 'overs_bowled', 0)):<{w_ov}}"
                f"{str(getattr(p, 'runs_conceded', 0)):<{w_r}}"
                f"{str(getattr(p, 'wickets', 0)):<{w_w}}"
                "\n"
            )
            chart.insert(tk.END, row)

        self.select_innings_tab(inn)


if __name__ == "__main__":
    root = tk.Tk()
    app = CricketGUI(root)
    root.mainloop()