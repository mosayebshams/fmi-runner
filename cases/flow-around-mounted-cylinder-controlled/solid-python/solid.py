from __future__ import division

import argparse
import numpy as np
import precice

parser = argparse.ArgumentParser()
parser.add_argument("configurationFileName",
                    help="Name of the xml config file.", type=str)

try:
    args = parser.parse_args()
except SystemExit:
    print("")
    print("Usage: python3 ./solverdummy.py precice-config")
    quit()

# system parameters

mass 		= 0.03575 # kg
k_spring 	= 69.48 # N/m
d_damper 	= 0.0043 # N/s

state_vector_old 	= np.zeros((3,1))
state_vector 		= np.zeros((3,1))

# testing parameters
ratio_force = 1

def update(mass, k_spring, d_damper, state_vector_old, dt, force, displacement_spring):
	
    # create system matrix for left hand side
    system_matrix = np.zeros((3,3))
    system_matrix[0,0] = 2/dt
    system_matrix[1,0] = k_spring
    system_matrix[0,1] = -1
    system_matrix[1,1] = 2*mass/dt + d_damper
    system_matrix[2,1] = 2/dt
    system_matrix[2,2] = -1
    
    # create A and c for right hand side
    A = np.zeros((3,3))
    A[0,0] = 2/dt
    A[0,1] = 1
    A[1,1] = 2*mass/dt
    A[2,1] = 2/dt
    A[1,2] = mass
    A[2,2] = 1
    
    c = np.zeros((3,1))
    c[1,0] = force + k_spring*displacement_spring
    
    # compute right hand side
    right_hand = A * state_vector_old + c
    
    # compute values for next time step
    state_vector = np.linalg.solve(system_matrix, right_hand)
    
    return state_vector
	

configuration_file_name = args.configurationFileName

participant_name = "Solid"
write_data_name = "Displacement-Cylinder"
read_data_name_force = "Force"
read_data_name_displacement = "Displacement-Spring"
mesh_name = "Mesh-Solid"

num_vertices = 1  # Number of vertices

solver_process_index = 0
solver_process_size = 1

interface = precice.Interface(participant_name, configuration_file_name,
                              solver_process_index, solver_process_size)

mesh_id = interface.get_mesh_id(mesh_name)

assert (interface.is_mesh_connectivity_required(mesh_id) is False)

dimensions = interface.get_dimensions()

vertices = np.zeros((num_vertices, dimensions))
read_data = np.zeros((num_vertices, dimensions))
write_data = np.zeros((num_vertices, dimensions))


vertex_ids = interface.set_mesh_vertices(mesh_id, vertices)
read_data_id_force = interface.get_data_id(read_data_name_force, mesh_id)
read_data_id_displacement = interface.get_data_id(read_data_name_displacement, mesh_id)
write_data_id = interface.get_data_id(write_data_name, mesh_id)

dt = interface.initialize()
t = 0

# initialize data
if interface.is_action_required(precice.action_write_initial_data()):
    interface.write_block_vector_data(write_data_id, vertex_ids, write_data)
    interface.mark_action_fulfilled(precice.action_write_initial_data())
interface.initialize_data()

while interface.is_coupling_ongoing():
    if interface.is_action_required(precice.action_write_iteration_checkpoint()):
        
        print("Writing checkpoint")
        state_vector_old_cp = state_vector_old
        state_vector_cp = state_vector
        
        interface.mark_action_fulfilled(precice.action_write_iteration_checkpoint())

    read_data_force = interface.read_block_vector_data(read_data_id_force, vertex_ids)
    force = read_data_force[0,1]
    read_data_displacement = interface.read_block_vector_data(read_data_id_displacement, vertex_ids)
    displacement_spring = read_data_displacement[0,1]
    
    # compute next time step
    state_vector = update(mass, k_spring, d_damper, state_vector_old, dt, force, displacement_spring)
	
	# cylinder is fixed in x-direction
    write_data[0,0] = 0
    
    # cylinder moves in y-direction according to spring-damper-mass-equation
    write_data[0,1] = state_vector[0,0]


    interface.write_block_vector_data(write_data_id, vertex_ids, write_data)

    print("Solid: Advancing in time")
    dt = interface.advance(dt)

    if interface.is_action_required(precice.action_read_iteration_checkpoint()):
        
        print("Reading checkpoint")
        state_vector_old = state_vector_old_cp
        state_vector = state_vector_cp
        
        interface.mark_action_fulfilled(precice.action_read_iteration_checkpoint())
    else:
    	state_vector_old = state_vector
    	t = t + dt

interface.finalize()
