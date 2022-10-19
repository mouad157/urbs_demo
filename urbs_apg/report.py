import os
import pathlib
import sqlite3 as sql

import pandas as pd
import pyomo.core

from .output import get_constants, \
    get_timeseries_aseangrid, calc_fixcost, calc_varcost, calc_invcost, \
    calc_fuelcost, entity_to_sql


def input_data_report(prob, filename, sce):
    """Write input data summary to a sqlite database

        Args:
            - prob: a urbs model instance;
            - filename: Excel spreadsheet filename, will be overwritten if exists;
    """

    # matrix to list
    prob._data["demand"] = prob._data["demand"].stack(0)
    # drop duplicated columns
    for df in prob._data:
        for c in prob._data[df].columns.intersection(
                prob._data[df].index.names):
            prob._data[df].drop([c], axis=1, inplace=True)
        if not prob._data[df].empty:
            prob._data[df]['Scenario'] = sce

    with sql.connect(str(filename)) as conn:
        for df in prob._data:
            prob._data[df].to_sql(df, conn, if_exists='append')

    return


def report(instance:pyomo.core.ConcreteModel, resultdir: pathlib.Path, sce: str,
           input_report:bool=True,
           *args, **kwargs):
    """Write result summary to spreadsheet files

    Args:
        - instance: a urbs model instance;
        - resultdir: output dir
        - filename: Excel spreadsheet filename, will be overwritten if exists;
        - sce: scenario name;
        - input_report: export input parameter as database
    Output:
        A spreadsheet named by scenario, including annual level data for Trans, Proc and Cost
        Other variables and dual info is stored in sqlite database.
    """

    if input_report:
        input_data_report(instance, pathlib.Path(resultdir, "Input.db"), sce)
    merge_cells = False

    if instance.timesteps:
        created, transmitted, stored, balance = get_timeseries_aseangrid(instance)
    """
    created:
        Columns: [Bioenergy, Bioenergy-ccs, Coal, Coal-ccs, Gas, Gas-ccs, Geothermal, 
                Hydro, Oil, Solar, Solar_w_battery, Wind]
        Index: ['t', 'stf', 'sit', 'com']
    transmitted:
        Columns: ['exported', 'imported', 'residue', 'utilization']
        Index: ['t', 'stf', 'sit', 'sit_', 'tra', 'com']
    balance:
        matrix of created by tech, exported, imported

        Columns: [Bioenergy, Bioenergy-ccs, Coal, Coal-ccs, Gas, Gas-ccs, Geothermal, 
                Hydro, Oil, Solar, Solar_w_battery, Wind, import, export]
        Index: ['t', 'stf', 'sit', 'com']
    """
    #==============================================================================
    #===============Annual data====================================================
    #For tableau to plot

    costs, cpro, ctra, csto = get_constants(
        instance)  # overall costs by type, capacity (total and new) for pro, tra, sto

    print(sce, costs)

    """cpro: annual level data for each process or trade (import, export)
    index = ['Year', 'Site', 'Process']
    column: capacity (total, new); Generation (CO2, Elec); Cost(Inv, Fix, Var, Fuel)
    """
    balance = balance.stack().unstack(0).sum(axis=1).unstack("com")
    balance.index.names = ['Year', 'Site', 'Process']
    cpro = pd.concat([cpro, balance], axis=1, keys=["Capacity", "Generation"])
    cpro[('Cost', 'Invest')] = calc_invcost(cpro, instance, 'process')
    cpro[('Cost', 'Fix')] = calc_fixcost(cpro, instance, 'process')
    cpro[('Cost', 'Var')] = calc_varcost(cpro[('Generation', 'Elec')], instance, 'process')
    cpro[('Cost', 'Fuel')] = calc_fuelcost(instance, 'process')
    cpro["Scenario"] = sce

    if instance.mode["tra"]:
        def trans_line_index(key):
            key = (key.From[''], key.To[''])
            if key[0] < key[1]:
                return [*key, 0]
            else:
                return [*key[::-1], 1]
        """ctra
            index = ['Year', 'site1', 'site2', 'Direction']
            columns = capacity (total and new), 
                    transmission (exported, imported(after loss), residue), 
                    utilization,
                    scenario
                    Cost (Invest, Fix, Var, Fuel)           
        """

        # sum transmission data over t
        transmitted = transmitted[["exported", "imported", "residue"]].unstack(0).sum(axis=1, level=0)
        ctra = pd.concat([ctra, transmitted], axis=1, keys=["Capacity", "Transmission"]).fillna(
            0)  # concat throughput info to ctra
        ctra["utilization"] = ctra[("Transmission", "exported")] / (
                ctra[("Capacity", "Total")] * instance.dt.value)  # calculate utilization
        ctra["Scenario"] = sce
        ctra[('Cost', 'Invest')] = calc_invcost(ctra, instance, 'transmission') / 2
        ctra[('Cost', 'Fix')] = calc_fixcost(ctra, instance, 'transmission') / 2
        ctra[('Cost', 'Var')] = 0
        ctra[('Cost', 'Fuel')] = 0
        ctra = ctra.rename_axis(index={'Site In': 'From', 'Site Out': 'To'})

        ctra.reset_index(inplace=True)
        ctra[['site1', 'site2', 'Direction']] = ctra.apply(trans_line_index, axis=1, result_type='expand')

        ctra = ctra.set_index(['Year', 'site1', 'site2', 'Direction'])

    #annual cost data (by year and type)
    costs_by_year = (cpro['Cost'].groupby('Year').sum() + ctra['Cost'].groupby('Year').sum()
                     ).unstack(0).reorder_levels([1, 0]).sort_index()
    costs_by_year = pd.DataFrame({'Costs': costs_by_year, 'Scenario': sce})
    #combine two levels of column index
    cpro.columns = cpro.columns.map('.'.join).str.strip('.')
    ctra.columns = ctra.columns.map('.'.join).str.strip('.')

    # Output to excel
    filename = resultdir/ "Scenarios"
    if not filename.is_dir(): filename.mkdir()
    filename = filename/ f"{sce}.xlsx"
    with pd.ExcelWriter(filename) as writer:
        # write constants to spreadsheet
        # costs.to_frame().to_excel(writer, 'Costs')
        costs_by_year.to_excel(writer, "Costs", merge_cells=merge_cells)
        cpro.to_excel(
            writer, 'Proc', merge_cells=merge_cells)
        # Capacity by technology by country by year, two structures:
        if instance.mode["tra"]:  ctra.to_excel(
            writer, 'Trans', merge_cells=merge_cells)
        if instance.mode["sto"]:  csto.to_excel(writer, 'Storage caps')

    """write to sqlite database
    
    result.db
    - Proc: annual level data for each process (and export, import), 
            including capacity, annual generation, and costs
    - Cost: annual level total costs by year and type
    - Trans: annual level transmission line data
            including capacity, annual throughput, and costs 
            costs are divided by 2 to ensure that it sums up to the correct value
    - Other variables: e_co_stock(commodity), e_pro_in (input), e_pro_out (output)
    - Dual variables for constraints:
        'res_vertex': balance for each node (time step, node) - marginal generation cost
        'res_env_total': dual var for emission constraint (per year, node) - marginal abatement cost
        'res_process_throughput_by_capacity': shadow price to add extra capacity for each tech
        'res_transmission_input_by_capacity': shadow price to add extra capacity for each line
    """
    with sql.connect(str(resultdir/"result.db")) as conn:
        cpro.to_sql('Proc', conn, if_exists='append')
        costs_by_year.to_sql('Cost', conn, if_exists='append')
        if instance.mode["tra"]:      ctra.to_sql('Trans', conn, if_exists='append')

        for var in ['e_co_stock', 'e_pro_in', 'e_pro_out']:
            entity_to_sql(instance, var, conn, sce, 'Var')
        if hasattr(instance, 'dual'):
            for constraint in ['res_vertex', 'res_env_total',
                           'res_process_throughput_by_capacity',
                           'res_transmission_input_by_capacity']:
                entity_to_sql(instance, constraint, conn, sce, 'Dual')


