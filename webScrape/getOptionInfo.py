import requests
import pandas as pd
import html5lib

import os
import sys
from pathlib import Path 
sys.path.append('/home/michael/jupyter/local-packages')

from localUtilities import dateUtils
from localUtilities.ibUtils import getOptionPrice

pd.set_option('display.max_rows', 1000)

theBaseCompaniesDirectory = '/home/michael/jupyter/earningDateData/Companies/'

csvSuffix = '.csv'
excelSuffix = '.xlsx'

#=========================================================================
def getOccVolume(symbol):
    s = requests.Session()
    #ONN Volume Search
    url = 'https://www.theocc.com/webapps/series-search'
    r = s.post(url,data={'symbolType': 'U','symbolId': symbol})
    # check to make sure passing a valid symbol
    try:
        df = pd.read_html(r.content)[0]
    except ValueError:
        print('     ', ValueError, 'In getOptionInfo.getOccVolume')
        print('              Symbol: ', symbol)
        df = pd.DataFrame()
        print('              df.empty: ', df.empty)
        return df
    df.columns = df.columns.droplevel()
    # Combine Cents/Decimal in Strike price
    df['Strike'] = df['Integer'] + (df['Dec']*0.001)
    cols_of_interest=['Product Symbol', 'Year', 'Month', 'Day', 'Strike', 'Call', 'Put']
    df = df[cols_of_interest]
    # get an expiry info
    df['expiry'] = df.apply(lambda x: dateUtils.toExpiryStr(x.Year, x.Month, x.Day), axis = 1)

    return df


def getOptionVolumeNextFriExpiryCount(aSymbol, startDay):
    """
Calculate the next Friday total Call / Put Open Interest
If there are no options for Friday goto Monthly else return O
    Parameters
    ----------
    aSymbol : Stock

    startDay : Earnings week

    Returns
    -------
    Volume of Call / Put open interest
    """

    # get OCC Volume for aSymbol
    aOccVolumeDF = getOccVolume(aSymbol)
    # if aOccVolumeDF is empty send back 0 and empty DF
    if aOccVolumeDF.empty:
        print('returning Empty')
        return (0, 0)
    else:
        print('not returing empty')


    # Get the Volume for Next Friday Option Strikes
    aOccVolumeDFNextWeek = aOccVolumeDF.loc[(aOccVolumeDF.expiry ==
                                            dateUtils.nextFridayOrgFormat(dateUtils.getDateFromISO8601(startDay)))]
    if aOccVolumeDFNextWeek.empty: #nothing for Next Friday?
        # Get the Volume for Next Friday Monthly Option Strikes
        aOccVolumeDFNextMontlyExpiry = aOccVolumeDF.loc[aOccVolumeDF.expiry ==
                                                        dateUtils.getNextThirdFridayFromDate(dateUtils.getDateFromISO8601(startDay))]
        theCallsOpenInterest = aOccVolumeDFNextMontlyExpiry.Call.sum()
        thePutsOpenInterest = aOccVolumeDFNextMontlyExpiry.Put.sum()
    else: #use puts/calls for next Friday
        theCallsOpenInterest = aOccVolumeDFNextWeek.Call.sum()
        thePutsOpenInterest = aOccVolumeDFNextWeek.Put.sum()

    return theCallsOpenInterest, thePutsOpenInterest



def getOptionVolume(aSymbol, aPrice, startDay):
    """

    Parameters
    ----------
    aSymbol : Stock
    aPrice : the Max or Min move for a closing price
    startDay : Earnings week

    Returns
    -------
    Tuples: ([0] strikePlus, [1] strikeMinus, [2] aOccVolumeDFNextWeek, [3] aOccVolumeDFNextMontlyExpiry)
        strikePlus/strikeMinus: Strike bounds Plus/Minus from aPrice - to id Min/Max parameters
        aOccVolumeDFNextWeek: Option Volume for next week
        aOccVolumeDFNextMontlyExpiry: Option Volume for next Monthly Expiry
    """
    # todo - if next week equals next expiry push out next expiry

    # get OCC Volume for aSymbol
    aOccVolumeDF = getOccVolume(aSymbol)

    # if aOccVolumeDF is empty send back 0 and empty DF
    if aOccVolumeDF.empty:
        return (0, 0, pd.DataFrame(), pd.DataFrame())

    strikePlus, strikeMinus = getStrikes(aPrice, aOccVolumeDF, startDay)

    # get list of OCC strikes between <= strikePlus and >= StrikeMinus
    strikes = [strike for strike in aOccVolumeDF.Strike
               if (strike >= strikeMinus and strike <= strikePlus)]

    # get the Volume for Strikes
    aOccVolumeDF = aOccVolumeDF[aOccVolumeDF.Strike.isin(strikes)]
    # Get the Volume for Next Friday Option Strikes
    aOccVolumeDFNextWeek = aOccVolumeDF.loc[(aOccVolumeDF.expiry ==
                                            dateUtils.nextFridayOrgFormat(dateUtils.getDateFromISO8601(startDay)))]

    # Get the Volume for Next Friday Monthly Option Strikes
    aOccVolumeDFNextMontlyExpiry = aOccVolumeDF.loc[aOccVolumeDF.expiry ==
                                                    dateUtils.getNextThirdFridayFromDate(dateUtils.getDateFromISO8601(startDay))]

    return (strikePlus, strikeMinus, aOccVolumeDFNextWeek, aOccVolumeDFNextMontlyExpiry)

def getStrikes(aPrice, aOccVolumeDF, startDay):

    # Compute interested Strike Prices
    # if price >= then $40 Get to the next round at +/- 5
    # if price < $40 get to round at the +/-2
    if aPrice >= 40:
        strikePlus = (5 * round(aPrice / 5)) + 10
        strikeMinus = (5 * round(aPrice / 5)) - 10
        # print('strikePlus', strikePlus)
        # print('strikeMinus', strikeMinus)
    elif aPrice >= 20:
        strikePlus = (2 * round(aPrice / 2)) + 5
        strikeMinus = (2 * round(aPrice / 2)) - 5
    else:
        strikePlus = (2 * round(aPrice / 2)) + 2
        strikeMinus = (2 * round(aPrice / 2)) - 2

    strikePlus, strikeMinus = checkStrikePrices(strikePlus, strikeMinus, aOccVolumeDF, startDay)

    return strikePlus, strikeMinus

def checkStrikePrices(strikePlus, strikeMinus, aOccVolumeDF, startDay):

    aOccVolumeDFpd = pd.DataFrame(aOccVolumeDF)

    nextThrdFri = dateUtils.getNextThirdFridayFromDate(dateUtils.getDateFromISO8601(startDay))
    nexFriday = dateUtils.nextFridayOrgFormat(dateUtils.getDateFromISO8601(startDay))

    listOfExpiryNextThrdFriday = aOccVolumeDFpd.loc[aOccVolumeDFpd['expiry'] == nextThrdFri]
    listOfExpiryNextFriday = aOccVolumeDFpd.loc[aOccVolumeDFpd['expiry'] == nexFriday]

    #todo make sure the +2 amnd -2 are good adjustments
    if listOfExpiryNextFriday.Strike.min() > strikeMinus:
        strikeMinus=listOfExpiryNextFriday.Strike.min() +2

    if listOfExpiryNextFriday.Strike.max() < strikePlus:
        strikePlus=listOfExpiryNextFriday.Strike.max() -2


    return strikePlus, strikeMinus


def addMinMaxDFsToExcel(maxDF, minDF, yahooEarningDfRow, aSymbol, writer):

    # add yahooEarningsDFRow with Header
    # add some color to Header
    # keep track of Excel Rows

    # skip some rows

    # get CSV earnings info for aSymbol
    # keep track of Excel Rows

    maxDF.to_excel(writer, sheet_name=aSymbol)
    minDF.to_excel(writer, sheet_name=aSymbol, startcol=10)

def getMinMaxVolsSaveAsCSV(ib, yahooEarningDf, startday):

    aMaxRight = 'C'
    aMinRight ='P'

    for i in range(0, len(yahooEarningDf)):
        aSymbol = yahooEarningDf.loc[i,].Symbol

        print('working: ', aSymbol )

        aMaxPrice = yahooEarningDf.loc[i,]['Max$MoveCl']
        #todo handle if getOptionVol return empty

        # getOptionVol returns
        # Tuple: ([0] strikePlus, [1] strikeMinus, [2] aOccVolumeDFNextWeek, [3] aOccVolumeDFNextMontlyExpiry)
        # [2] aOccVolumeDFNextWeek - may be empty if only Monthly options

        maxMoveTuples = getOptionVolume(aSymbol, float(yahooEarningDf.loc[i,]['Max$MoveCl'][1:]), startday)
        minMoveTuples = getOptionVolume(aSymbol, float(yahooEarningDf.loc[i,]['Min$MoveCl'][1:]), startday)
        # todo not sure how to work this
        #       if there is no Volume info from OCC
        if maxMoveTuples[2].empty and maxMoveTuples[3].empty:
            print('min-maxMoveTuples.empty for symbol: ', aSymbol)
            continue

        # print('maxMoveTuples = \n', maxMoveTuples)
        # print('minMoveTuples = \n', minMoveTuples)

        # print('maxMoveTuples[2] = \n', maxMoveTuples[2].expiry[:1].values[0])
        # print('minMoveTuples[2] = \n', minMoveTuples[2].expiry[:1].values[0])

        # print('maxMoveTuples[2].empty: ', maxMoveTuples[2].empty)

        if maxMoveTuples[2].empty:
            nextFriIndexMax = pd.MultiIndex.from_product([[maxMoveTuples[3].expiry[:1].values[0]],
                                                          list(maxMoveTuples[3].Strike)], names=['Expiry', 'Strikes'])

            nextFriIndexMin = pd.MultiIndex.from_product([[minMoveTuples[3].expiry[:1].values[0]],
                                                          list(minMoveTuples[3].Strike)], names=['Expiry', 'Strikes'])

            dfNextFriMax = pd.DataFrame(list(maxMoveTuples[3].Call), index=nextFriIndexMax, columns=['Call Volume'])

            dfNextFriMin = pd.DataFrame(list(minMoveTuples[3].Put), index=nextFriIndexMin, columns=['Put Volume'])

        else:
            nextFriIndexMax = pd.MultiIndex.from_product([[maxMoveTuples[2].expiry[:1].values[0]],
                                                          list(maxMoveTuples[2].Strike)], names=['Expiry', 'Strikes'])

            nextFriIndexMin = pd.MultiIndex.from_product([[minMoveTuples[2].expiry[:1].values[0]],
                                                          list(minMoveTuples[2].Strike)], names=['Expiry', 'Strikes'])

            dfNextFriMax = pd.DataFrame(list(maxMoveTuples[2].Call), index=nextFriIndexMax, columns=['Call Volume'])

            dfNextFriMin = pd.DataFrame(list(minMoveTuples[2].Put), index=nextFriIndexMin, columns=['Put Volume'])


        expiryIndexMax = pd.MultiIndex.from_product([[maxMoveTuples[3].expiry[:1].values[0]],
                                                     list(maxMoveTuples[3].Strike)], names=['Expiry', 'Strikes'])

        expiryIndexMin = pd.MultiIndex.from_product([[minMoveTuples[3].expiry[:1].values[0]],
                                                     list(minMoveTuples[3].Strike)], names=['Expiry', 'Strikes'])

        dfExpiryMax = pd.DataFrame(list(maxMoveTuples[3].Call), index=expiryIndexMax, columns=['Call Volume'])


        dfExpiryMax = getOptionPrice.getStockOptionPrice(ib, aSymbol, dfExpiryMax, aMaxRight, yahooEarningDf.loc[i,].close)
        dfNextFriMax = getOptionPrice.getStockOptionPrice(ib, aSymbol, dfNextFriMax, aMaxRight, yahooEarningDf.loc[i,].close)

        dfExpiryMin = pd.DataFrame(list(minMoveTuples[3].Put), index=expiryIndexMin, columns=['Put Volume'])


        dfExpiryMin = getOptionPrice.getStockOptionPrice(ib, aSymbol, dfExpiryMin, aMinRight, yahooEarningDf.loc[i,].close)
        dfNextFriMin = getOptionPrice.getStockOptionPrice(ib, aSymbol, dfNextFriMin, aMinRight, yahooEarningDf.loc[i,].close)

        framesMax = [dfExpiryMax, dfNextFriMax]
        framesMin = [dfExpiryMin, dfNextFriMin]

        #todo - add the symbol name to the new dataframe as a column
        maxDF = pd.concat(framesMax) #,  keys=[aSymbol])
        minDF = pd.concat(framesMin) #,  keys=[aSymbol])

        saveMinMaxDF2CSV(maxDF, minDF, aSymbol, startday)

    return

def saveMinMaxDF2CSV(maxDF, minDF, aSymbol, startday):

    theDirectory = '/home/michael/jupyter/earningDateData/' + 'Companies/' + startday + '/'
    csvSuffix = '.csv'
    aStockOutFile = theDirectory + aSymbol + '-MinMaxDF' + csvSuffix

    maxDF.to_csv(aStockOutFile, mode='a', header=True)
    minDF.to_csv(aStockOutFile, mode='a', header=True)


def saveSummaryToExcel(yahooEarningsDF, startday ):
    """

    Parameters
    ----------
    yahooEarningsDF: the Yahoo earnings DF
    startday : Earnings week startday

    Returns
    -------

    """

    # Setup Excel output file
    companyEarningsWeek = theBaseCompaniesDirectory + startday + '/'
    outExcelFile = companyEarningsWeek + 'SummaryWeekOf-' + startday + excelSuffix

    # Create a Pandas Excel writer using XlsxWriter as the engine
    # assuming Path is setup
    writer = pd.ExcelWriter(outExcelFile, engine='xlsxwriter')

    summaryWorkbook = writer.book

    # Summary Sheet Name
    yahooEarningsDF.to_excel(writer, sheet_name='Summary Earnings')

    for i in range(0, len(yahooEarningsDF)):
        aSymbol = yahooEarningsDF.loc[i,].Symbol
        theHeader = yahooEarningsDF.loc[i,].to_frame()
        theHeaderTransposed = theHeader.T
        theHeaderTransposed.to_excel(writer, sheet_name= aSymbol)

        inCsvFile_aSymbol = companyEarningsWeek + aSymbol + csvSuffix
        yahooEarningsDf_aSymbol = pd.read_csv(inCsvFile_aSymbol, index_col=0)
        startRow = len(yahooEarningsDf_aSymbol) + 3
        yahooEarningsDf_aSymbol.to_excel(writer, sheet_name= aSymbol,  startrow=startRow)

    # Convert the dataframe to an XlsxWriter Excel object.
    # yahooEarningDf.to_excel(writer, sheet_name='Week of ' + startday)

    # Close the Pandas Excel writer and output the Excel file.
    writer.save()

    return

def saveDiary2Excel(ib, startday):

    companyEarningsWeek = theBaseCompaniesDirectory + startday + '/'

    # Get saved Summary data
    earningWeekDir = Path(companyEarningsWeek)

    # Save Week Summary
    companySummaryListFile = 'SummaryOfWeek-' + startday + csvSuffix

    # read in CSV summary file based on startday
    yahooEarningsDF = pd.read_csv(earningWeekDir / companySummaryListFile, index_col=0)

    # save Put/Call Volumes to CSV files
    getMinMaxVolsSaveAsCSV(ib, yahooEarningsDF, startday)
    # save the weeks earning Summary to Excel
    saveSummaryToExcel(yahooEarningsDF, startday)

    return
