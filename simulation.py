#!/usr/bin/env python
import sys
import argparse
from time import sleep
from vrep import *
from util import *
from controller import *
from twiddle import *


class SimulationController(object):
    """
    A class for running the simulation. Mostly useful for holding data such as
    the client object.
    """

    def __init__(self, client, controller_class=SegwayController, tuner_class=Twiddle):
        self.client = client
        # Instantiate controller and tuner objects from the provided classes
        self.controller = controller_class(client)
        self.tuner = tuner_class()

    def setup(self, body="body", left_motor="leftMotor", right_motor="rightMotor"):
        """
        Setup object handles and possible other V-REP related things.
        """
        self.controller.setup_body('body')
        self.controller.setup_motors('leftMotor', 'rightMotor')

    def setup_tuner(self, **kwargs):
        self.tuner.setup(**kwargs)

    def single_run(self, parameters):
        """
        A function to pass for the twiddle implementation. [P, I, D] -> error
        """
        # Create a PID by parameters
        P, I, D = parameters
        balance_PID = PID(P, I, D, 0.0, 0.0)
        self.controller.setup_control(balance_PID)
        log(self.client, 'New simulation with (%f, %f, %f)' % (P, I, D))
        # Start the simulation (1st clear velocities)
        self.controller.set_target_velocities(0.0, 0.0)
        err = simxStartSimulation(self.client, simx_opmode_oneshot_wait)
        if err > 1:
            log(self.client, 'ERROR StartSimulation code %d' % err)
        # Do the control, returns when end condition is reached
        cost, niterations = self.controller.run()
        # Stop the simulation (e.g. fell down, time up)
        err = simxStopSimulation(self.client, simx_opmode_oneshot_wait)
        if err > 1:
            log(self.client, 'ERROR StopSimulation code %d' % err)
        log(self.client, 'Simulation results to cost %f (#%d)' % (cost, niterations))
        # Wait some time to prevent V-REP lagging behind
        sleep(0.1)
        return cost

    def run(self):
        """
        Run the simulation continuously and tune the parameters. Ctrl-Cs are
        caught on the self.tuner.tune function. Returns the best parameters.
        """
        return self.tuner.tune(self.single_run)


##############################################################################
# MAIN 50ms: 21.000000 9.009500 16.550000
#      10ms: 79.0 19.9 41.4
##############################################################################
if __name__ == '__main__':
    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--one-shot", action="store_true", help="Do a single")
    parser.add_argument("-p", "--params", nargs=3, type=float, metavar="P", help="PID gains in a list: [KP, KI, KD]", default=[10, 5, 5])
    parser.add_argument("-d", "--deltas", nargs=3, type=float, metavar="dP", help="Twiddle PID gain deltas in a list: [dKP, dKI, dKD]", default=[10,5,5])
    args = parser.parse_args()

    print '-- Starting master client'

    # Close all connection, just in case
    simxFinish(-1)

    # localhost:19997 connects to V-REP global remote API
    addr = '127.0.0.1'
    port = 19997
    print '-- Connecting to %s:%d' % (addr, port)
    client = simxStart(addr, port, True, True, 5000, 5)

    if client != -1:
        log(client, 'Master client connected to client %d at port %d' % (client, port))

        err, objs = simxGetObjects(client, sim_handle_all, simx_opmode_oneshot_wait)
        if err == simx_return_ok:
            log(client, 'Number of objects in the scene: %d' % len(objs))
        else:
            log(client, 'ERROR GetObjects code %d' % err)

        # Create a simulation controller to run the tuning
        simulation_controller = SimulationController(client)
        # Defaults will do for the setup unless we change the model
        simulation_controller.setup()

        # Tuning run
        if not args.one_shot:
            # Setup twiddle
            simulation_controller.setup_tuner(params=args.params, deltas=args.deltas)
            # Run tuner
            best_params = simulation_controller.run()
            print str(best_params)

        # One shot
        else:
            simulation_controller.single_run(map(float, args.params))  # [sys.argv[1], sys.argv[2], sys.argv[3]]

        # Force stop of simulation under all circumstances
        print "-- Enter simulation stop enrage! [while(stop)]"
        while simxStopSimulation(client, simx_opmode_oneshot_wait): pass
    else:
        print '-- Failed connecting to remote API server'

    print '-- Terminating master client'
