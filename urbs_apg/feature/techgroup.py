import pyomo.core as pyomo


def add_tech_group_constraints(self):
    """Add tech group constraints

    Examples:
        >>> from urbs_apg.feature import techgroup
        >>> prob = urbs.create_model(data)
        >>> prob.add_tech_group_constraints()

    Args:
        self: problem

    Returns:

    """
    if self._data.get('techgroup', None) is None:
        print("No tech group is defined.")
        return
    techgroup_member = self._data['techgroup'].to_dict('list')
    self.techgroup_dict = self._data['techgroup_process'].to_dict()

    indexlist = set(techgroup_member.keys())
    self.techgroup = pyomo.Set(
        initialize=indexlist,
        doc='Set of technology group that share the same cap-up and cap-lo')
    self.techgroup_member = pyomo.Set(
        self.techgroup,
        initialize=techgroup_member,
        doc='The member technologies of each tech group'
    )

    self.techgroup_tuples = pyomo.Set(
        within=self.stf * self.sit * self.techgroup,
        initialize=tuple(self.techgroup_dict["cap-lo"].keys()),
        doc='Combinations of possible tech group, e.g. (2018,North,solar)')

    self.res_techgroup_capacity = pyomo.Constraint(
        self.techgroup_tuples,
        rule=res_techgroup_capacity_rule,
        doc='techgroup.cap-lo <= total tech group capacity <= techgroup.cap-up')
    return self.res_techgroup_capacity

pyomo.ConcreteModel.add_tech_group_constraints = add_tech_group_constraints

def res_techgroup_capacity_rule(m, stf, sit, tg):
    return (m.techgroup_dict['cap-lo'][stf, sit, tg],
            sum(m.cap_pro[stf, sit, pro] for pro in m.techgroup_member[tg]),
            m.techgroup_dict['cap-up'][stf, sit, tg])
