import threading
import time
import random
from abc import ABC, abstractmethod


# ======= TIME SETTINGS =======


SECONDS_PER_HOUR = 5.0
DAY_SECONDS = 120.0  # 1 day = 120 seconds
SHIP_STAY_HOURS = 8
SHIP_STAY_SECONDS = SHIP_STAY_HOURS * SECONDS_PER_HOUR  # 8h -> 40s
LAST_CALL_MINUTES = 30
LAST_CALL_SECONDS = (LAST_CALL_MINUTES / 60.0) * SECONDS_PER_HOUR  # 0.5h -> 2.5s


ARRIVAL_WINDOW_START = 8
ARRIVAL_WINDOW_END = 10


NUM_SHIPS_PER_DAY = 5
PASSENGERS_PER_SHIP = 50  # change to 200 when ready


# ======= GLOBAL STATE & STATS =======


random_lock = threading.Lock()
print_lock = threading.Lock()
stranded_lock = threading.Lock()


stranded_passengers = []
dead_passengers = []


stats = {
   "died_cliff": 0,
   "died_shark": 0,
   "drunk": 0,
   "intoxicated": 0,
   "popup_delay": 0,
   "fell_asleep": 0,
   "lost_hiking": 0,
   "snorkel_delay": 0,
   "stranded": 0,
   "boarded": 0,
   "total_passengers": 0
}




def safe_print(*args, **kwargs):
   with print_lock:
       print(*args, **kwargs)




# ======= STRATEGY PATTERN =======


class MovementStrategy(ABC):
   @abstractmethod
   def travel_time(self, dist):
       pass




class WalkStrategy(MovementStrategy):
   def travel_time(self, dist):
       return dist / 1.0




class BusStrategy(MovementStrategy):
   def travel_time(self, dist):
       return dist / 3.0




class TaxiStrategy(MovementStrategy):
   def travel_time(self, dist):
       return dist / 4.0




TRANSPORT_STRATEGIES = {
   "walk": WalkStrategy(),
   "bus": BusStrategy(),
   "taxi": TaxiStrategy(),
}




# ======= LOCATION =======


class Location:
   def __init__(self, name, max_capacity, base_hours, dist):
       self.name = name
       self.max_capacity = max_capacity
       self.base_duration = base_hours * SECONDS_PER_HOUR
       self.distance = dist
       self.count = 0
       self.lock = threading.Lock()


   def try_enter(self, pid):
       with self.lock:
           if self.count < self.max_capacity:
               self.count += 1
               safe_print(f"[LOC] P{pid} entered {self.name} ({self.count}/{self.max_capacity})")
               return True
       return False


   def leave(self, pid):
       with self.lock:
           self.count -= 1
           safe_print(f"[LOC] P{pid} left {self.name} ({self.count}/{self.max_capacity})")




# ======= FACTORY METHOD =======


class PassengerFactory:
   @classmethod
   def create(cls, pid, ship_id):
       age_group = random.choice(["young", "adult", "senior"])
       gender = random.choice(["male", "female"])
       strength = random.randint(30, 100)
       stats["total_passengers"] += 1
       return Passenger(pid, ship_id, age_group, gender, strength)




# ======= PASSENGER (OBSERVER) =======


class Passenger(threading.Thread):
   def __init__(self, pid, ship_id, age_group, gender, strength):
       super().__init__()
       self.passenger_id = pid
       self.ship_id = ship_id
       self.age_group = age_group
       self.gender = gender
       self.strength = strength
       self.ship = None
       self.current_location = None
       self.transport_strategy = TRANSPORT_STRATEGIES["walk"]
       self.on_board = False
       self.was_drunk = False
       self.is_dead = False
       self.daemon = True


   def attach_to_ship(self, ship):
       self.ship = ship
       ship.attach(self)


   def choose_transport(self):
       choice = random.choice(list(TRANSPORT_STRATEGIES.keys()))
       self.transport_strategy = TRANSPORT_STRATEGIES[choice]
       return choice


   def choose_activity(self, locations):
       weights = []
       for loc in locations:
           if "bar" in loc.name:
               weights.append(3 if self.age_group == "young" else 2)
           elif "beach" in loc.name:
               weights.append(3)
           else:
               weights.append(1)
       with random_lock:
           return random.choices(locations, weights=weights, k=1)[0]


   def go_to_location(self, location):
       if self.is_dead:
           return
       mode = self.choose_transport()
       travel = self.transport_strategy.travel_time(location.distance)
       safe_print(f"[MOVE] P{self.passenger_id} using {mode} to {location.name} (t={travel:.1f}s)")
       time.sleep(travel)
       if location.try_enter(self.passenger_id):
           self.current_location = location


   def stay_in_activity(self):
       if self.is_dead or not self.current_location:
           return


       loc = self.current_location
       loc_name = loc.name
       end_time = time.time() + loc.base_duration


       # normal stay until duration or last call
       while time.time() < end_time:
           if self.is_dead:
               return
           if self.ship.last_call_event.is_set():
               break
           time.sleep(0.5)


       # ======= RARE DEATH EVENTS =======


       if loc_name == "hiking_excursion" and random.random() < 0.02:
           self.is_dead = True
           dead_passengers.append(self)
           stats["died_cliff"] += 1
           safe_print(f"[💀 DEATH] P{self.passenger_id} fell off a cliff at hiking_excursion.")
           return


       if loc_name == "snorkeling_excursion" and random.random() < 0.02:
           self.is_dead = True
           dead_passengers.append(self)
           stats["died_shark"] += 1
           safe_print(f"[💀 DEATH] P{self.passenger_id} was eaten by a shark while snorkeling.")
           return


       # ======= RARE DELAYS / INCIDENTS =======


       # Restaurants: intoxicated (5%)
       if "restaurant" in loc_name and random.random() < 0.05:
           extra = random.uniform(1, 2)
           stats["intoxicated"] += 1
           safe_print(f"[🍷 INTOXICATED] P{self.passenger_id} stayed longer in {loc_name} "
                      f"({extra:.1f}s)")
           time.sleep(extra)


       # Bars: drunk (7%)
       if "bar" in loc_name and random.random() < 0.07:
           extra = random.uniform(2, 3)
           stats["drunk"] += 1
           safe_print(f"[🍺 DRUNK] P{self.passenger_id} got drunk in {loc_name} ({extra:.1f}s)")
           time.sleep(extra)
           self.was_drunk = True


       # Shopping: pop-up (4%)
       if loc_name == "shopping_street" and random.random() < 0.04:
           extra = random.uniform(2, 4)
           stats["popup_delay"] += 1
           safe_print(f"[🛍 POP-UP] P{self.passenger_id} stuck at pop-up ({extra:.1f}s)")
           time.sleep(extra)


       # Hiking: lost (3%)
       if loc_name == "hiking_excursion" and random.random() < 0.03:
           extra = random.uniform(3, 5)
           stats["lost_hiking"] += 1
           safe_print(f"[🥾 LOST] P{self.passenger_id} got lost hiking ({extra:.1f}s)")
           time.sleep(extra)


       # Snorkeling: delay (3%)
       if loc_name == "snorkeling_excursion" and random.random() < 0.03:
           extra = random.uniform(3, 5)
           stats["snorkel_delay"] += 1
           safe_print(f"[🌊 LATE SWIM] P{self.passenger_id} struggled swimming ({extra:.1f}s)")
           time.sleep(extra)


       # Beach: fell asleep (4%)
       if loc_name == "paradise_beach" and random.random() < 0.04:
           extra = random.uniform(2, 4)
           stats["fell_asleep"] += 1
           safe_print(f"[😴 ASLEEP] P{self.passenger_id} fell asleep at the beach ({extra:.1f}s)")
           time.sleep(extra)


   def return_to_ship(self):
       if self.is_dead:
           return


       # extra drunk reaction delay (5%)
       if self.was_drunk and random.random() < 0.05:
           delay = random.uniform(1, 2)
           safe_print(f"[🍺 DRUNK-DELAY] P{self.passenger_id} reacted late ({delay:.1f}s)")
           time.sleep(delay)


       travel = TRANSPORT_STRATEGIES["taxi"].travel_time(0.5)
       safe_print(f"[RETURN] P{self.passenger_id} rushing via taxi (t={travel:.1f}s)")
       time.sleep(travel)


       if not self.ship.departed_event.is_set():
           self.on_board = True
           stats["boarded"] += 1
           safe_print(f"[BOARD] P{self.passenger_id} boarded ship {self.ship_id} on time")
       else:
           stats["stranded"] += 1
           safe_print(f"[MISS] P{self.passenger_id} missed ship {self.ship_id}")


   def run(self):
       if self.is_dead or self.ship is None:
           return


       safe_print(f"[WAIT] P{self.passenger_id} waiting for ship {self.ship_id}")
       self.ship.arrived_event.wait()


       if self.is_dead:
           return


       safe_print(f"[ARRIVE] P{self.passenger_id} disembarked from ship {self.ship_id}")


       locations = self.ship.island.locations


       while not self.ship.departed_event.is_set():
           if self.is_dead:
               return


           loc = self.choose_activity(locations)
           self.go_to_location(loc)


           if self.current_location:
               self.stay_in_activity()
               if self.is_dead:
                   return
               self.current_location.leave(self.passenger_id)
               self.current_location = None


           if self.ship.last_call_event.is_set():
               self.return_to_ship()
               break


       if not self.on_board and not self.is_dead:
           with stranded_lock:
               stranded_passengers.append(self)
           safe_print(f"[STRANDED] P{self.passenger_id} stranded from ship {self.ship_id}")




# ======= SHIP =======


class CruiseShip(threading.Thread):
   def __init__(self, ship_id, island, arrival_hour):
       super().__init__()
       self.ship_id = ship_id
       self.island = island
       self.arrival_offset = (arrival_hour - ARRIVAL_WINDOW_START) * SECONDS_PER_HOUR
       self.arrived_event = threading.Event()
       self.last_call_event = threading.Event()
       self.departed_event = threading.Event()
       self.observers = []
       self.daemon = True


   def attach(self, passenger):
       self.observers.append(passenger)


   def notify_last_call(self):
       safe_print(f"[SHIP {self.ship_id}] 🔔 Last call for passengers!")
       self.last_call_event.set()


   def notify_departure(self):
       safe_print(f"[SHIP {self.ship_id}] 🚢 Departing now")
       self.departed_event.set()


   def run(self):
       safe_print(f"[SHIP {self.ship_id}] Scheduled arrival t={self.arrival_offset:.1f}s")
       time.sleep(self.arrival_offset)
       safe_print(f"[SHIP {self.ship_id}] Arrived at island")
       self.arrived_event.set()


       time.sleep(SHIP_STAY_SECONDS - LAST_CALL_SECONDS)
       self.notify_last_call()


       time.sleep(LAST_CALL_SECONDS)
       self.notify_departure()




# ======= EVENT MANAGER =======


class EventManager(threading.Thread):
   def __init__(self, island):
       super().__init__()
       self.island = island
       self.stop_event = threading.Event()
       self.daemon = True


   def run(self):
       while not self.stop_event.is_set():
           time.sleep(random.randint(5, 15))
           evt = random.choice(["rain", "transport", "festival"])


           if evt == "rain":
               safe_print("[EVENT] 🌧 Rainstorm started")
               time.sleep(5)
               safe_print("[EVENT] 🌦 Rainstorm ended")


           elif evt == "transport":
               mode = random.choice(list(TRANSPORT_STRATEGIES.keys()))
               safe_print(f"[EVENT] 🚧 Transport breakdown: {mode}")
               time.sleep(5)
               safe_print(f"[EVENT] ✅ {mode} restored")


           elif evt == "festival":
               safe_print("[EVENT] 🎉 Festival pop-up triggered near shopping_street")
               time.sleep(5)
               safe_print("[EVENT] 🎉 Festival ended")




# ======= HUNGER GAMES =======


class HungerGames:
   @staticmethod
   def run(stranded):
       safe_print(f"[HUNGER] 👾 Starting hunger games with {len(stranded)} stranded passengers")


       if dead_passengers:
           safe_print("[HUNGER] ☠ Passengers who died earlier today:")
           for p in dead_passengers:
               safe_print(f"    - P{p.passenger_id} (strength {p.strength})")


       fighters = list(stranded)
       random.shuffle(fighters)


       while len(fighters) > 1:
           a = fighters.pop()
           b = fighters.pop()
           total = a.strength + b.strength
           r = random.randint(1, total)
           winner = a if r <= a.strength else b


           safe_print(f"[HUNGER] P{a.passenger_id} (str {a.strength}) vs "
                      f"P{b.passenger_id} (str {b.strength}) -> winner P{winner.passenger_id}")


           fighters.append(winner)
           time.sleep(0.2)


       if fighters:
           safe_print(f"[HUNGER] 🏆 Ultimate survivor: P{fighters[0].passenger_id}")
       else:
           safe_print("[HUNGER] No stranded passengers today")




# ======= ISLAND =======


class Island:
   def __init__(self):
       self.locations = [
           Location("mexican_restaurant", 40, 1.0, 1.0),
           Location("italian_restaurant", 40, 1.0, 1.2),
           Location("senor_frog_bar", 60, 1.5, 1.5),
           Location("irish_bar", 50, 1.5, 1.3),
           Location("shopping_street", 80, 1.0, 1.8),
           Location("hiking_excursion", 30, 2.0, 2.0),
           Location("snorkeling_excursion", 30, 2.0, 2.2),
           Location("paradise_beach", 100, 2.0, 1.0),
       ]


       self.ships = []
       self.event_manager = EventManager(self)


   def setup_day(self):
       self.event_manager.start()


       for sid in range(1, NUM_SHIPS_PER_DAY + 1):
           with random_lock:
               arrival_hour = random.uniform(ARRIVAL_WINDOW_START, ARRIVAL_WINDOW_END)


           ship = CruiseShip(sid, self, arrival_hour)
           self.ships.append(ship)
           ship.start()


           for i in range(PASSENGERS_PER_SHIP):
               pid = sid * 1000 + i
               p = PassengerFactory.create(pid, sid)
               p.attach_to_ship(ship)
               p.start()


   def run_hunger_games(self):
       self.event_manager.stop_event.set()
       HungerGames.run(stranded_passengers)




# ======= MAIN =======


def main():
   island = Island()
   island.setup_day()


   for ship in island.ships:
       ship.join()


   time.sleep(3)
   island.run_hunger_games()


   # ======= END-OF-DAY STATS =======
   safe_print("\n" + "=" * 60)
   safe_print("               🌴 END OF DAY STATISTICS 🌴")
   safe_print("=" * 60)
   safe_print(f"Total passengers:       {stats['total_passengers']}")
   safe_print(f"Boarded ships:          {stats['boarded']}")
   safe_print(f"Stranded passengers:    {stats['stranded']}")
   safe_print(f"Deaths:    {stats['died_shark']+stats['died_cliff']}")
   safe_print("")
   safe_print("---- ACTIVITY INCIDENTS ----")
   safe_print(f"Got drunk:              {stats['drunk']}")
   safe_print(f"Intoxicated:            {stats['intoxicated']}")
   safe_print(f"Pop-up delays:          {stats['popup_delay']}")
   safe_print(f"Fell asleep:            {stats['fell_asleep']}")
   safe_print(f"Lost while hiking:      {stats['lost_hiking']}")
   safe_print(f"Snorkeling delays:      {stats['snorkel_delay']}")
   safe_print("")
   safe_print("---- DEATHS ----")
   safe_print(f"Shark attacks:          {stats['died_shark']}")
   safe_print(f"Fell off a cliff:       {stats['died_cliff']}")
   safe_print("=" * 60)




if __name__ == "__main__":
   main()

