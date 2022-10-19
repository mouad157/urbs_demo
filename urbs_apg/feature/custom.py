import pyomo.core as pyomo

def add_custom_constraints(self, **kwargs) -> tuple:
    """usage: custom_constraints = model.add_custom_constraints()

    Args:
        self:

    Returns:
        tuples of custom constraints

    """
    # New capacity for solar after 2030 <= 0
    self.no_more_solar_set = pyomo.Set(initialize={i for i in self.pro_tuples if i[0] > 2030 and i[2] == 'Solar'})

    self.res_no_more_solar_after_2030 = pyomo.Constraint(self.no_more_solar_set,
                                                         rule=res_no_more_new_capacity_rule,
                                                         doc="New capacity for solar after 2030 <= 0"
                                                         )

    # Each year, the share of VRE (variable renewable energy, including solar and wind) does not
    # exceed 50% of total demand of the whole region
    self.res_vre_limit = pyomo.Constraint(self.stf,
                                          rule=res_vre_limit_rule,
                                          doc='Variable renewable energy does not exceed 50% of ASEAN total generation')

    # Each country and year, domestic generation must supply a minimum ratio of its domestic demand
    # Equivalent to: net import (import*loss-export) must not exceed (1-demand.min-ratio) of its total demand
    self.pro_capfactor_tuples = pyomo.Set(
        within=self.stf * self.sit * self.pro,
        initialize=[(stf, sit, pro)
                    for (stf, sit, pro) in self.pro_tuples
                    if self.process_dict['cap_factor'][stf, sit, pro] < 1.0],
        doc='Processes with maximum capacity factor')

    self.res_throughput_by_capacity_factor = pyomo.Constraint(self.pro_capfactor_tuples,
        rule=res_generation_capacity_factor,
        doc='8760 * cap_pro * cap_factor >= annual tau_pro')

    def res_generation_total_rule(m, stf, sit, com, com_type):
        if com not in m.com_demand:
            return pyomo.Constraint.Skip
        else:
            return sum(m.e_pro_out[tm, stf, sit, process, com]
                       for tm in m.tm
                       for stframe, site, process in m.pro_tuples
                       if site == sit and stframe == stf and
                       (stframe, process, com) in m.r_out_dict) \
                   >= m.commodity_dict["min-ratio"][(stf, sit, com, com_type)] * sum(
                m.demand_dict[(sit, com)][(stf, tm)] for tm in m.tm)

    if self.commodity_dict.get("min-ratio"):
        self.res_import_limit = pyomo.Constraint(
            self.com_tuples,
            rule=res_generation_total_rule,
            doc='demand generation >= commodity.min-ratio * demand'
        )



    return (self.res_no_more_solar_after_2030,
            self.res_vre_limit,
            self.res_no_more_solar_after_2030)

pyomo.ConcreteModel.add_custom_constraints = add_custom_constraints

def res_generation_capacity_factor(m, stf, sit, pro):
    return (sum(m.tau_pro[tm, stf, sit, pro] for tm in m.tm) * m.weight
            <= 8760 * m.cap_pro[stf, sit, pro] * m.process_dict['cap_factor'][stf, sit, pro])


def res_generation_total_rule(m, stf, sit, com, com_type):
    """Pyomo constraint: minimum domestic generation limit
    For (support timeframe, site, demand)
    domestic generation >= demand * min-ratio
    """
    if com not in m.com_demand:
        return pyomo.Constraint.Skip
    else:
        return sum(m.e_pro_out[tm, stf, sit, process, com]
                   for tm in m.tm
                   for stframe, site, process in m.pro_tuples
                   if site == sit and stframe == stf and
                   (stframe, process, com) in m.r_out_dict) \
               >= m.commodity_dict["min-ratio"][(stf, sit, com, com_type)] * sum(
            m.demand_dict[(sit, com)][(stf, tm)] for tm in m.tm)


def res_no_more_new_capacity_rule(m, stf, sit, pro):
    """Pyomo constraint: No new plants are allowed
    For (support timeframe, site, process)

    """
    return m.cap_pro_new[stf, sit, pro] <= 0


def res_vre_limit_rule(m, stf):
    """Pyomo Constraint: the share of VRE does not exceed 50%
    For the whole region

    """
    return sum(
        m.e_pro_out[t, stf, sit, proc, 'Elec'] for t in m.tm for (stf0, sit, proc, com) in
        m.pro_output_tuples
        if stf == stf0 and proc in ['Solar', 'Wind'] and com in m.com_demand) <= 0.5 * \
           sum(m.demand_dict[(sit, com)][(stf, tm)] for sit in m.sit for com in m.com_demand for tm in m.tm)
