import pathlib
from datetime import datetime

import pandas as pd


def to_excel(data: dict, overwrite_dir: pathlib.Path, modified_sheets: set, logger: str = '') -> None:
    """ Export data to excel

    Args:
        data:
        overwrite_dir:
        modified_sheets:
        logger:

    Returns:
        None

    """
    years = list(data["global_prop"].index.levels[0])
    years.sort()
    sheet_name_dict = {"global_prop": "Global",
                       "supim": "SupIm",
                       "dsm": "DSM",
                       "eff_factor": "TimeVarEff",
                       }

    if overwrite_dir:
        for year in years:
            with pd.ExcelWriter(str(overwrite_dir / f"{year}.xlsx"), mode="a",
                                if_sheet_exists="new") as writer:
                for sheet in modified_sheets:
                    if sheet in sheet_name_dict.keys():
                        s_name = sheet_name_dict[sheet]
                    else:
                        s_name = "-".join(i.capitalize() for i in sheet.split("_"))

                    try:
                        writer.book.remove(writer.book[s_name])
                    except:
                        pass
                    data[sheet].loc[year].to_excel(writer, s_name, merge_cells=False)
        if logger:
            changelog = overwrite_dir / "changelog.txt"
            with changelog.open('a') as f:
                f.write(f'\n{datetime.now().strftime("%Y-%h-%d %H:%m")}\n')
                f.write(logger)


def to_parquet(data: dict, overwrite_dir: pathlib.Path, logger: str = '') -> None:
    """ Write urbs dataframes to parquet format.

    Args:
        data: dictionary of dataframes
        overwrite_dir: output directory
        logger: [optional]

    Returns:
        None
    """
    import pyarrow.parquet as pq
    import pyarrow as pa

    if not overwrite_dir.is_dir():
        overwrite_dir.mkdir()

    for key in data.keys():
        pa.parquet.write_table(
            pa.Table.from_pandas(data[key]),
            overwrite_dir / f'{key}.parquet')

    # append the logger to the changelog file, if any
    if logger:
        changelog = overwrite_dir / "changelog.txt"
        with changelog.open('a') as f:
            f.write(f'\n{datetime.now().strftime("%Y-%h-%d %H:%m")}\n')
            f.write(logger)


def to_sqlite(data: dict, overwrite_dir: pathlib.Path, filename: str = 'Input_data.db'):
    """  Write urbs dataframes to sqlite database.

    Args:
        data: dict of urbs data
        overwrite_dir: database directory
        filename: database file name


    Returns:
        None
    """

    import sqlite3 as sql

    con = sql.connect(overwrite_dir / filename)
    for key in data:
        data[key].to_sql(key, con, if_exists='replace', )
    con.close()


def read_parquet(input_path: pathlib.Path) -> dict:
    """ Read parquet-format input file and prepare URBS input dict.

    Use parquet files for better input-output performance.

    Args:
        input_path: input_path to input directory;

    Returns:
        a dict of up to 12 DataFrames
    """
    data = {}
    if input_path.is_dir():
        for filename in input_path.glob('*.parquet'):
            data[filename.stem] = pd.read_parquet(filename)

    return data


def data_preprocess(data: dict) -> dict:
    """Pre-process data for urbs-apg model.

    usage:
        >>> data = data_prepocess(data)

    Add year weight (5) for the last support timeframe;
    Add capacity factor if the column does not exists;
    Change data type to float32 to avoid numerical error
    """
    print("data preprocess: add weight of 5 for 2050; change dtype to float32")

    data['global_prop'] = \
        data['global_prop'].append(pd.DataFrame([5], index=[(2050, "Weight")],
                                                columns=["value"]))
    if 'time_frac' in data['process'].columns:
        data['process'].rename(columns={'time_frac': 'cap_factor'}, inplace=True)
    if "cap_factor" not in data['process'].columns:
        data['process']["cap_factor"] = 1
    else:
        data['process'].loc[(data['process']['cap_factor'] > 1) |
                            (data['process']["cap_factor"].isnull()), "cap_factor"] = 1

    data['process'] = data['process'].astype('float32')
    return data
