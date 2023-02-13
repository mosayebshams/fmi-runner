from __future__ import division

import argparse
import numpy as np
import precice
import csv
import os
from fmpy import read_model_description, extract
from fmpy.fmi3 import FMU3Slave
from fmpy.simulation import Input, Recorder
from fmpy.util import write_csv
import shutil
import sys

### Load settings

parser = argparse.ArgumentParser()
parser.add_argument("settingFilePath", help="Path to the setting files fmuSettings and preciceSettings.", type=str)
args = parser.parse_args()

setting_file_path = args.settingFilePath

script_dir = os.path.dirname( __file__ )
file_dir = os.path.join( script_dir, setting_file_path )
sys.path.append(file_dir)

from fmuSettings import *
from preciceSettings import *

### FMU setup

model_description = read_model_description(fmu_file_name)  
vrs = {}
for variable in model_description.modelVariables:
    vrs[variable.name] = variable.valueReference 

parameter_names		= list(parameter.keys())
parameter_values		= list(parameter.values())
parameter_vr 			= [vrs.get(key) for key in parameter_names]

initial_conditions_names	= list(initial_conditions.keys())
initial_conditions_values	= list(initial_conditions.values())
initial_conditions_vr		= [vrs.get(key) for key in initial_conditions_names]


can_get_and_set_fmu_state	= model_description.coSimulation.canGetAndSetFMUstate
checkpoint_names		= list(checkpoint.keys())
checkpoint_vr			= [vrs.get(key) for key in checkpoint_names]

output_names		 	= list(output.keys())

vr_read  	 = [vrs[fmu_read_data_name]]
vr_write 	 = [vrs[fmu_write_data_name]]

unzipdir = extract(fmu_file_name)
fmu = FMU3Slave(guid=model_description.guid, unzipDirectory=unzipdir, modelIdentifier=model_description.coSimulation.modelIdentifier, instanceName=instance_name)

fmu.instantiate()

fmu.enterInitializationMode()

# Set parameters 
fmu.setFloat64(parameter_vr, parameter_values)
# Set initial conditions
fmu.setFloat64(initial_conditions_vr, initial_conditions_values)

fmu.exitInitializationMode()



# Get initial write data. Check this if using more than one read / write data point
fmu_write_data_init = fmu.getFloat64(vr_write)


### preCICE setup

interface = precice.Interface(participant_name, configuration_file_name, solver_process_index, solver_process_size)

mesh_id = interface.get_mesh_id(mesh_name)
dimensions = interface.get_dimensions()

vertex = np.zeros(dimensions)
read_data = np.zeros(num_vertices)

# initial value for write data
write_data = fmu_write_data_init * np.ones(num_vertices)


vertex_id = interface.set_mesh_vertex(mesh_id, vertex)
read_data_id = interface.get_data_id(read_data_name, mesh_id)
write_data_id = interface.get_data_id(write_data_name, mesh_id)

precice_dt = interface.initialize()
my_dt = precice_dt  # use my_dt < precice_dt for subcycling

# write initial data
if interface.is_action_required(precice.action_write_initial_data()):
    interface.write_scalar_data(write_data_id, vertex_id, write_data)
    interface.mark_action_fulfilled(precice.action_write_initial_data())

interface.initialize_data()

recorder = Recorder(fmu=fmu, modelDescription=model_description, variableNames=output_names)

t = 0

recorder.sample(t, force=False)

while interface.is_coupling_ongoing():
    if interface.is_action_required(precice.action_write_iteration_checkpoint()):
        
        if True: # can_get_and_set_fmu_state is currently read wrong by FMPy
            state_cp 	= fmu.getFMUState()
            print("Get_set works")
        elif len(checkpoint_names) != 0:
            checkpoint = fmu.getFloat64(checkpoint_vr)
        else:
            raise Exception('Please provide variables for the checkpoint during implicit coupling. The FMU model doesnt allow to \
            get and set the FMU state with the built-in functions.')
        t_cp = t
        
        interface.mark_action_fulfilled(precice.action_write_iteration_checkpoint())

    # compute time step size for this time step
    dt = np.min([precice_dt, my_dt])
    
    read_data = interface.read_scalar_data(read_data_id, vertex_id)
    data = read_data
    
    fmu.setFloat64(vr_read, [data])
    
    fmu.doStep(t, dt)

    result = fmu.getFloat64(vr_write)

    write_data = result[0]

    interface.write_scalar_data(write_data_id, vertex_id, write_data)

    t = t + dt
    
    precice_dt = interface.advance(dt)

    if interface.is_action_required(precice.action_read_iteration_checkpoint()):
        
        if True: # can_get_and_set_fmu_state is currently read wrong by FMPy
            fmu.setFMUState(state_cp)
        else:
            fmu.setFloat64(checkpoint_vr, checkpoint)
        
        t = t_cp
        interface.mark_action_fulfilled(precice.action_read_iteration_checkpoint())
        
    else:
        recorder.sample(t, force=False)



interface.finalize()

if not os.path.exists("output"):
    os.makedirs("./output")
    
# store final result
recorder.sample(t, force=False)
results = recorder.result()
write_csv(output_file_name, results)

fmu.terminate()
fmu.freeInstance()              
# clean up FMU
shutil.rmtree(unzipdir, ignore_errors=True)

