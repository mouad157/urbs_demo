import pandas as pd
import pyomo.core

from urbs.input import get_input
from urbs.pyomoio import get_entity, get_entities


def entity_to_sql(instance: pyomo.core.ConcreteModel, component_name: str, sql_conn, scenario: str, prefix: str=''):
    entityvalue = get_entity(instance, component_name)
    entityvalue = pd.concat([entityvalue], keys=[scenario], names=['Scenario'])
    entityvalue.to_sql(
        "_".join([prefix, component_name]).strip('_'), sql_conn, if_exists='append')

def calc_invcost(x, m, asset):
    '''

    Args:
        x: Capacity New (cap_tra_new)
        m: model
        asset: {'transmission', 'process', 'storage'}

    Returns: a series of invcost

    '''
    if m.mode['int']:
        factor = m._data[asset]['invcost-factor']-m._data[asset]['overpay-factor']
    else:
        factor = m._data[asset]['invcost-factor']

    cost = x[('Capacity', 'New')] * (factor
             * m._data[asset]['inv-cost']).rename_axis(index={'support_timeframe':'Year'})
    return cost


def calc_fixcost(x, m, asset):
    '''

    Args:
        x: capacity total
        m:

    Returns:

    '''
    return x[('Capacity', 'Total')] * (
            m._data[asset]['fix-cost']*
            m._data[asset]['cost_factor']
                ).rename_axis(index={'support_timeframe':'Year'}
                                                                                  )


def calc_varcost(x, m, asset):
    '''

    Args:
        x: e_tra_in
        m: model

    Returns:

    '''
    if asset == 'process':
        return x * (m._data[asset]['var-cost']  * m.weight() *m._data[asset]['cost_factor']
                ).rename_axis(index={'support_timeframe':'Year'})
    else:
        return 0


def calc_fuelcost(m, asset):
    if asset == 'process':
        idx = pd.IndexSlice

        pro_in = get_entity(m, 'e_pro_in').loc[
            idx[:, :, :, :, m.com_stock.data()]
        ].sum(
            level=[1, 2, 3, 4])



        pro_in = pro_in.reset_index().merge(
            m._data['commodity'][['price', 'cost_factor']], how='left',
            left_on=['stf', 'sit', 'com'],
            right_on=['support_timeframe', 'Site', 'Commodity']
                                      ).set_index(['stf', 'sit', 'pro', 'com'])
        def sum_cost(x):
            return x['price']*x['e_pro_in']*x['cost_factor']
        fuelprice = pro_in.apply(sum_cost, axis=1).sum(level=(0,1,2))


        return fuelprice
    else:
        return 0

def transmission_cost_by_year(m, cost_type, y):
    """returns transmission cost function for the different cost types

    Inv cost and  fixed cost are divided by 2.
    """

    if cost_type == 'Invest':
        cost = sum(m.cap_tra_new[t] *
                   m.transmission_dict['inv-cost'][t] *
                   m.transmission_dict['invcost-factor'][t]
                   for t in m.tra_tuples if t[0] == y) / 2

        if m.mode['int']:
            cost -= sum(m.cap_tra_new[t] *
                        m.transmission_dict['inv-cost'][t] *
                        m.transmission_dict['overpay-factor'][t]
                        for t in m.tra_tuples if t[0] == y) / 2

        return cost
    elif cost_type == 'Fixed':
        return sum(m.cap_tra[t] * m.transmission_dict['fix-cost'][t] *
                   m.transmission_dict['cost_factor'][t]
                   for t in m.tra_tuples if t[0] == y) / 2
    elif cost_type == 'Variable':
        if m.mode['dpf']:
            return sum(m.e_tra_in[(tm,) + t] * m.weight *
                       m.transmission_dict['var-cost'][t] *
                       m.transmission_dict['cost_factor'][t]
                       for tm in m.tm
                       for t in m.tra_tuples_tp if t[0] == y) + \
                   sum(m.e_tra_abs[(tm,) + t] * m.weight *
                       m.transmission_dict['var-cost'][t] *
                       m.transmission_dict['cost_factor'][t]
                       for tm in m.tm
                       for t in m.tra_tuples_dc if t[0] == y)
        else:
            '''return (((m._data['transmission']['cost_factor']
                     * m._data['transmission']['var-cost']).rename_axis(
                index={'support_timeframe': 'stf', 'Site In': 'sit', 'Site Out': 'sit_',
                       'Transmission': 'tra', 'Commodity': 'com'})) \
                   * get_entity(m, 'e_tra_in')).sum(level= [0,1,2])/2'''
            return sum(m.e_tra_in[(tm,) + t] * m.weight *
                       m.transmission_dict['var-cost'][t] *
                       m.transmission_dict['cost_factor'][t]
                       for tm in m.tm
                       for t in m.tra_tuples if t[0] == y) / 2



def get_constants(instance):
    """Return summary DataFrames for important variables

    Usage:
        costs, cpro, ctra, csto = get_constants(instance)

    Args:
        instance: an urbs model instance

    Returns:
        (costs, cpro, ctra, csto) tuple

    Example:
        >>> import pyomo.environ
        >>> from pyomo.opt.base import SolverFactory
        >>> data = read_excel('mimo-example.xlsx')
        >>> prob = create_model(data, range(1,25))
        >>> optim = SolverFactory('glpk')
        >>> result = optim.solve(prob)
        >>> cap_pro = get_constants(prob)[1]['Total']
        >>> cap_pro.xs('Wind park', level='Process').apply(int)
        Site
        Mid      13000
        North    23258
        South        0
        Name: Total, dtype: int64
    """
    costs = get_entity(instance, 'costs')
    cpro = get_entities(instance, ['cap_pro', 'cap_pro_new'])
    ctra = get_entities(instance, ['cap_tra', 'cap_tra_new'])
    csto = get_entities(instance, ['cap_sto_c', 'cap_sto_c_new',
                                   'cap_sto_p', 'cap_sto_p_new'])

    # better labels and index names and return sorted
    if not cpro.empty:
        cpro.index.names = ['Year', 'Site', 'Process']
        cpro.columns = ['Total', 'New']
        cpro.sort_index(inplace=True)
    if not ctra.empty:
        ctra.index.names = ['Year', 'Site In', 'Site Out',
                             'Transmission', 'Commodity']
        ctra.columns = ['Total', 'New']
        ctra.sort_index(inplace=True)
    if not csto.empty:
        csto.index.names = ['Year', 'Site', 'Storage', 'Commodity']
        csto.columns = ['C Total', 'C New', 'P Total', 'P New']
        csto.sort_index(inplace=True)

    return costs, cpro, ctra, csto

def get_transmissions(instance,  com):
    """Return DataFrames of transmission matrix and list

     Usage:
         df_transmission, list_transmission = get_transmissions(instance, com="Elec")

     Args:
         - instance: a urbs model instance
         - com: a commodity name

     Returns:
         a tuple of (df_transmission, sr_import) with
         DataFrames timeseries. These are:

         - df_transmission: matrix version of electricity flow
         - sr_import: list version of electricity flow
     """


    stf_sites = get_input(instance, "site").index.rename(["Year", "Region"])# get year-region index
    try:
        #init
        df_transmission = pd.DataFrame(index=stf_sites, columns=stf_sites.levels[1])

        sr_export = get_entity(instance, 'e_tra_in'). \
            xs([com], level=["com"]). \
            unstack(["t", "tra"]).sum(axis=1)#before loss

        sr_import = get_entity(instance, 'e_tra_out'). \
            xs([com], level=["com"]). \
            unstack(["t", "tra"]).sum(axis=1)  # after loss


        #eliminate possible simetricity and calculate net export between two sites
        #for stf in sr_export.index.levels[0]:
        #    for sit in sr_export.index.levels[1]:
        #        for sit_, value in sr_export.loc[(stf,sit)].iteritems():
        #            net_export = sr_export.loc[(stf, sit, sit_)]-sr_export.loc[(stf, sit_, sit)]
        #            sr_export.loc[(stf, sit, sit_)] = max(0, net_export)
        #            sr_export.loc[(stf, sit_, sit)] = max(0, -net_export)

        Net_transaction = pd.DataFrame({"Elec":-sr_export.sum(level=[0,1]),
                                        "Tech":"Export"})\
            .append(pd.DataFrame({"Elec":sr_import.sum(level=[0,2]),
                                        "Tech":"Import"})
                    ).reset_index().set_index(["stf", "sit","Tech"]).\
            sort_index().rename_axis(index=["Year", "Region", "Tech"])


        for (stf, sit, sit_),value in sr_export.iteritems():
            df_transmission[sit_][stf, sit]=value



        sr_util = sr_export/get_entity(instance, "cap_tra").xs(
            "Elec", level="com").reset_index("tra", drop=True)*instance.weight()/8760




        #diagnal values: internal transmission = production - total export
        production = get_entity(instance, "e_pro_out").xs(com, level="com").sum(level=("stf", "sit"))
        for (stf, sit),value in production.iteritems():
            df_transmission[sit][stf, sit]=value - \
                                           sr_export.sum(level=("stf", "sit")).get((stf, sit),0)
            sr_export.loc[stf, sit, sit]=df_transmission[sit][stf, sit]


        list_transmission = pd.concat([sr_export,sr_util], axis=1,
                                      keys=(com + "(MWh)", "Utilization")).rename_axis(["Year", "From", "To"])

    except:
        #df_transmission = pd.DataFrame()
        Net_transaction=pd.DataFrame()
        list_transmission = pd.DataFrame()
    return Net_transaction, list_transmission

def get_com_list_annual(instance, com):
    return get_entity(instance, "e_pro_out").xs([com], level=["com"]). \
        unstack("t").sum(axis=1).replace(0,pd.NaT).rename_axis(index=["Year", "Region", "Tech"])

def get_timeseries_aseangrid(instance, timesteps=None):

    """Return DataFrames of all timeseries referring to given commodity

    Usage:
        created, consumed, stored, imported, exported,
        dsm = get_timeseries(instance, commodity, sites, timesteps)

    Args:
        - instance: a urbs model instance
        - com: a commodity name
        - sites: a site name or list of site names
        - timesteps: optional list of timesteps, default: all modelled
          timesteps

    Returns:
        a tuple of (created, consumed, storage, imported, exported, dsm) with
        DataFrames timeseries. These are:

        - created: timeseries of commodity creation, i.g. Electricity and CO2
        - transmitted: timeseries of commodity import, i.e. Electricity
        - storage: time series of commodity storage, i.e. Electricity

        - balance: join of created, import and export,
    """
    if timesteps is None:
        # default to all simulated timesteps
        timesteps = sorted(get_entity(instance, 'tm').index)
    else:
        timesteps = sorted(timesteps)  # implicit: convert range to list


    # DEMAND
    # default to zeros if commodity has no demand, get timeseries

    # PROCESS output from each process
    created = get_entity(instance, 'e_pro_out') #index: (t, stf, sit, com); column: generation
    try:
        created = created.loc[timesteps]
        created = created.unstack(level='pro').fillna(0)
    except KeyError:
        created = pd.DataFrame(index=timesteps)

    # if commodity is transportable
    try:
        imported = get_entity(instance, 'e_tra_out').loc[timesteps] #out: after loss
        exported = get_entity(instance, 'e_tra_in').loc[timesteps]
        #production = created.xs(["Elec"], level=["com"]).sum(axis=1)

        total_imports = imported.sum(level=["t","stf","sit_","com"]).rename("imports") #sum over the "From" column
        total_imports.index.rename("sit",level=2,inplace=True) #sum over the "To" column
        balance=created.join(total_imports)

        total_exports = -exported.sum(level=["t","stf","sit","com"]).rename("exports")
        total_exports.index.rename("sit",level=2,inplace=True) #sum over the "To" column
        balance=balance.join(total_exports)

        # Calculate utilization
        # if transmission capacity = 0, fill the utilization as 0 (filtered in visualization)
        residue = -exported + (get_entity(
            instance, "cap_tra"))*instance.dt.value
        sr_util = exported/(get_entity(
            instance, "cap_tra")*instance.dt.value)
        #sr_util=sr_util.reorder_levels([4,0,1,2,3]).fillna(0)
        # internal transmission: internal transmission = production - total export
        #for (t, stf, sit),value in production.iteritems():
        #    imported.loc[t, stf, sit, sit, "Elec"]=value + \
        #                                   total_exports.get((t,stf,sit,"Elec"),0)
        #    exported.loc[t, stf, sit, sit, "Elec"]=imported.loc[t, stf, sit, sit, "Elec"]



        transmitted = pd.concat([ exported,imported, residue, sr_util], axis=1,
                                keys=["exported","imported","residue", "utilization"])



    except KeyError:
        # imported and exported are empty
        transmitted = pd.DataFrame(index= timesteps)
    # if storage is allowed
    try:
        stored = get_entities(instance, ['e_sto_con', 'e_sto_in', 'e_sto_out'])
        stored = stored.loc[timesteps].sum(level=[0,1,2,4])
        stored.columns = ['Level', 'Storage(charging)', 'Storage(discharging)']
        balance=balance.join(stored['Storage(charging)','Storage(discharging)' ])

        #created = created.join(stored)


    except KeyError:
        # storage empty
        stored = pd.DataFrame(index= timesteps)
        pass

    # show throughput of stock /the output of commodity

    balance.sort_index()
    return created, transmitted, stored, balance

def get_dual(instance, constraint):
    return get_entity(instance, constraint)

def drop_all_zero_columns(df):
    """ Drop columns from DataFrame if they contain only zeros.

    Args:
        df: a DataFrame

    Returns:
        the DataFrame without columns that only contain zeros
    """
    return df.loc[:, (df != 0).any(axis=0)]
