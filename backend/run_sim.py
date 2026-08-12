from dotenv import load_dotenv
load_dotenv()

from app.simulation.simulator import run_simulation

run_simulation("mobile_checkout_fee")

