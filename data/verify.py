import wntr

network_file = "l_town.inp"

wn = wntr.network.WaterNetworkModel(network_file)

print("Network loaded successfully!")
print("junctions:", len(wn.junction_name_list))
print("pipes:", len(wn.pipe_name_list))
print("reservoirs:", len(wn.reservoir_name_list))

sim = wntr.sim.EpanetSimulator(wn)
results = sim.run_sim()

print("Simulation completed successfully!")